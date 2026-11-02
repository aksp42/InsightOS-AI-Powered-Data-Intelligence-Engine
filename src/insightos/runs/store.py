"""Run directories, the immutable original input, and atomic artifact persistence.

Layout (Blueprint V2 section 12)::

    <runs_dir>/<run_id>/
        manifest.json
        input/ profile/ detection/ scoring/ llm/ cleaning/ validation/ report/

Guarantees: the original upload is copied byte-for-byte, hashed (SHA-256) and made read-only;
artifacts are written atomically; an existing artifact is never overwritten unless asked; run ids
and artifact names are validated so they cannot escape the run directory.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from insightos import __version__
from insightos.errors import (
    ArtifactError,
    ArtifactExistsError,
    ArtifactNotFoundError,
    ImmutableInputError,
    RunError,
    RunExistsError,
)
from insightos.runs.models import InputFileRef, RunManifest, RunPhase
from insightos.schemas import VersionedArtifact

if TYPE_CHECKING:
    from insightos.settings import Settings

MANIFEST_NAME = "manifest.json"
LOG_NAME = "run.log"

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_CHUNK = 1024 * 1024

A = TypeVar("A", bound=VersionedArtifact)


def new_run_id(now: datetime | None = None) -> str:
    """``YYYYMMDDTHHMMSSZ-<8 hex>``: sortable by time, unique within a second."""
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return f"{moment:%Y%m%dT%H%M%S}Z-{secrets.token_hex(4)}"


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise RunError(
            f"unsafe run id {run_id!r}: use 1-64 characters from A-Z a-z 0-9 . _ - "
            "starting with a letter or digit"
        )


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", Path(name).name).lstrip(".")
    return cleaned[:200] or "input"


def _write_atomic(path: Path, text: str, *, overwrite: bool) -> None:
    """Write ``text`` to ``path`` via a temp file in the same directory; no partial files."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(0o644)
        if overwrite:
            os.replace(tmp, path)
            return
        try:
            os.link(tmp, path)  # atomic "create only if absent"
        except FileExistsError:
            raise ArtifactExistsError(f"artifact already exists: {path.name}") from None
        except OSError:  # hard links unsupported on this filesystem: best-effort fallback
            if path.exists():
                raise ArtifactExistsError(f"artifact already exists: {path.name}") from None
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _sha256_of(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


@dataclass(frozen=True)
class Run:
    """Handle to one run directory."""

    run_id: str
    root: Path

    @property
    def log_path(self) -> Path:
        return self.root / LOG_NAME

    # --- manifest ----------------------------------------------------------------------
    def read_manifest(self) -> RunManifest:
        path = self.root / MANIFEST_NAME
        try:
            return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise RunError(f"cannot read manifest for run {self.run_id}: {exc}") from exc

    def _write_manifest(self, manifest: RunManifest) -> None:
        _write_atomic(
            self.root / MANIFEST_NAME, manifest.model_dump_json(indent=2) + "\n", overwrite=True
        )

    # --- original input ----------------------------------------------------------------
    def store_input_file(self, source: Path) -> InputFileRef:
        """Copy the original upload into ``input/`` byte-for-byte, hash it, make it read-only."""
        source = Path(source)
        if not source.is_file():
            raise RunError(f"input file not found: {source}")
        manifest = self.read_manifest()
        if manifest.input_file is not None:
            raise ImmutableInputError(f"run {self.run_id} already has an original input")

        input_dir = self.root / RunPhase.INPUT.value
        stored_name = _safe_filename(source.name)
        dest = input_dir / stored_name
        if dest.exists():
            raise ImmutableInputError(f"input already exists: {stored_name}")

        digest = hashlib.sha256()
        size = 0
        fd, tmp_name = tempfile.mkstemp(dir=input_dir, prefix=".tmp-", suffix=".part")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out, source.open("rb") as src:
                while chunk := src.read(_CHUNK):
                    out.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                out.flush()
                os.fsync(out.fileno())
            tmp.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)

        ref = InputFileRef(
            original_filename=source.name,
            stored_path=f"{RunPhase.INPUT.value}/{stored_name}",
            sha256=digest.hexdigest(),
            size_bytes=size,
        )
        try:
            self._write_manifest(manifest.model_copy(update={"input_file": ref}))
        except Exception:
            dest.chmod(0o644)
            dest.unlink(missing_ok=True)
            raise
        return ref

    def input_path(self) -> Path:
        """Path of the stored original input (must stay inside ``input/``)."""
        ref = self.read_manifest().input_file
        if ref is None:
            raise RunError(f"run {self.run_id} has no stored input")
        path = (self.root / ref.stored_path).resolve()
        if not path.is_relative_to((self.root / RunPhase.INPUT.value).resolve()):
            raise RunError(f"manifest input path escapes the input directory: {ref.stored_path}")
        return path

    def verify_input(self) -> bool:
        """True iff the stored input still matches the SHA-256 and size in the manifest."""
        ref = self.read_manifest().input_file
        if ref is None:
            raise RunError(f"run {self.run_id} has no stored input")
        path = self.input_path()
        if not path.is_file():
            return False
        digest, size = _sha256_of(path)
        return digest == ref.sha256 and size == ref.size_bytes

    # --- artifacts ---------------------------------------------------------------------
    def artifact_path(self, phase: RunPhase, name: str) -> Path:
        if not _ARTIFACT_NAME_RE.fullmatch(name):
            raise ArtifactError(
                f"unsafe artifact name {name!r}: use 1-100 characters from A-Z a-z 0-9 . _ - "
                "starting with a letter or digit"
            )
        return self.root / RunPhase(phase).value / f"{name}.json"

    def write_artifact(
        self, phase: RunPhase, name: str, artifact: VersionedArtifact, *, overwrite: bool = False
    ) -> Path:
        """Persist ``artifact`` atomically. Refuses to replace an existing one by default."""
        path = self.artifact_path(phase, name)
        _write_atomic(path, artifact.model_dump_json(indent=2) + "\n", overwrite=overwrite)
        return path

    def read_artifact(self, phase: RunPhase, name: str, model: type[A]) -> A:
        """Load and validate an artifact; a schema-version mismatch is an error."""
        path = self.artifact_path(phase, name)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ArtifactNotFoundError(f"artifact not found: {phase.value}/{name}") from None
        except (OSError, UnicodeDecodeError) as exc:
            raise ArtifactError(f"cannot read artifact {phase.value}/{name}: {exc}") from exc
        try:
            return model.model_validate_json(text)
        except ValidationError as exc:
            raise ArtifactError(f"artifact {phase.value}/{name} failed validation: {exc}") from exc


class RunStore:
    """Creates and opens runs under a root directory (default: ``Settings.runs_dir``)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @classmethod
    def from_settings(cls, settings: Settings) -> RunStore:
        return cls(settings.runs_dir)

    def create_run(self, run_id: str | None = None) -> Run:
        rid = new_run_id() if run_id is None else run_id
        _validate_run_id(rid)
        self.root.mkdir(parents=True, exist_ok=True)
        run_root = self.root / rid
        try:
            run_root.mkdir()
        except FileExistsError:
            raise RunExistsError(f"run already exists: {rid}") from None
        for phase in RunPhase:
            (run_root / phase.value).mkdir()
        run = Run(run_id=rid, root=run_root)
        run._write_manifest(RunManifest(run_id=rid, insightos_version=__version__))
        return run

    def open_run(self, run_id: str) -> Run:
        _validate_run_id(run_id)
        run_root = self.root / run_id
        if not (run_root / MANIFEST_NAME).is_file():
            raise RunError(f"no such run: {run_id}")
        return Run(run_id=run_id, root=run_root)
