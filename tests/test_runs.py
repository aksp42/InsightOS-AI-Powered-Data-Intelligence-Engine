"""Run directory layout, immutable input handling, and artifact persistence."""

from __future__ import annotations

import hashlib
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from insightos.errors import (
    ArtifactError,
    ArtifactExistsError,
    ArtifactNotFoundError,
    ImmutableInputError,
    RunError,
    RunExistsError,
)
from insightos.runs import Run, RunPhase, RunStore, new_run_id
from insightos.schemas import VersionedArtifact

EXPECTED_PHASE_DIRS = {
    "input",
    "profile",
    "detection",
    "scoring",
    "llm",
    "cleaning",
    "validation",
    "report",
}


class Note(VersionedArtifact):
    SCHEMA_VERSION: ClassVar[str] = "1.0"

    text: str


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.fixture
def run(store: RunStore) -> Run:
    return store.create_run()


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "my data (1).csv"
    path.write_bytes(b"id,name\n001,Asha\n002,  Ravi \n")
    return path


# --- run ids and layout ---------------------------------------------------------------
def test_run_id_format_and_uniqueness() -> None:
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", new_run_id())
    assert len({new_run_id() for _ in range(50)}) == 50


def test_run_id_embeds_timestamp() -> None:
    moment = datetime(2026, 10, 22, 5, 55, 0, tzinfo=UTC)
    assert new_run_id(moment).startswith("20261022T055500Z-")


def test_phase_enum_matches_approved_layout() -> None:
    assert {phase.value for phase in RunPhase} == EXPECTED_PHASE_DIRS


def test_create_run_builds_phase_directories_and_manifest(run: Run) -> None:
    assert {p.name for p in run.root.iterdir() if p.is_dir()} == EXPECTED_PHASE_DIRS
    manifest = run.read_manifest()
    assert manifest.run_id == run.run_id
    assert manifest.input_file is None


def test_duplicate_run_id_is_rejected(store: RunStore) -> None:
    store.create_run("fixed-id")
    with pytest.raises(RunExistsError):
        store.create_run("fixed-id")


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "..", ".hidden", "with space", "x" * 200])
def test_unsafe_run_ids_are_rejected(store: RunStore, bad: str) -> None:
    with pytest.raises(RunError):
        store.create_run(bad)
    with pytest.raises(RunError):
        store.open_run(bad)


def test_open_run_roundtrip_and_missing(store: RunStore, run: Run) -> None:
    assert store.open_run(run.run_id).root == run.root
    with pytest.raises(RunError):
        store.open_run("no-such-run")


# --- original input -------------------------------------------------------------------
def test_store_input_file_preserves_bytes_and_records_hash(run: Run, csv_file: Path) -> None:
    content = csv_file.read_bytes()
    ref = run.store_input_file(csv_file)

    stored = run.input_path()
    assert stored.read_bytes() == content  # byte-for-byte, no parsing (leading zeros intact)
    assert ref.sha256 == hashlib.sha256(content).hexdigest()
    assert ref.size_bytes == len(content)
    assert ref.original_filename == "my data (1).csv"
    assert ref.stored_path == "input/my_data__1_.csv"
    assert run.read_manifest().input_file == ref
    assert csv_file.exists()  # the source is copied, never moved


def test_stored_input_is_read_only(run: Run, csv_file: Path) -> None:
    run.store_input_file(csv_file)
    assert stat.S_IMODE(run.input_path().stat().st_mode) == 0o444


def test_second_input_is_refused(run: Run, csv_file: Path, tmp_path: Path) -> None:
    run.store_input_file(csv_file)
    other = tmp_path / "other.csv"
    other.write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(ImmutableInputError):
        run.store_input_file(other)


def test_missing_source_file_is_rejected(run: Run, tmp_path: Path) -> None:
    with pytest.raises(RunError):
        run.store_input_file(tmp_path / "nope.csv")


def test_verify_input_detects_tampering(run: Run, csv_file: Path) -> None:
    run.store_input_file(csv_file)
    assert run.verify_input() is True
    path = run.input_path()
    path.chmod(0o644)
    path.write_bytes(b"tampered")
    assert run.verify_input() is False


def test_input_path_requires_a_stored_input(run: Run) -> None:
    with pytest.raises(RunError):
        run.input_path()
    with pytest.raises(RunError):
        run.verify_input()


# --- artifacts ------------------------------------------------------------------------
def test_artifact_roundtrip(run: Run) -> None:
    path = run.write_artifact(RunPhase.PROFILE, "note", Note(text="hello"))
    assert path == run.root / "profile" / "note.json"
    loaded = run.read_artifact(RunPhase.PROFILE, "note", Note)
    assert loaded.text == "hello"
    assert loaded.schema_version == "1.0"


def test_existing_artifact_is_not_overwritten_by_default(run: Run) -> None:
    run.write_artifact(RunPhase.PROFILE, "note", Note(text="first"))
    with pytest.raises(ArtifactExistsError):
        run.write_artifact(RunPhase.PROFILE, "note", Note(text="second"))
    assert run.read_artifact(RunPhase.PROFILE, "note", Note).text == "first"
    run.write_artifact(RunPhase.PROFILE, "note", Note(text="second"), overwrite=True)
    assert run.read_artifact(RunPhase.PROFILE, "note", Note).text == "second"


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "..", ".hidden", "x y", "x" * 200])
def test_unsafe_artifact_names_are_rejected(run: Run, bad: str) -> None:
    with pytest.raises(ArtifactError):
        run.write_artifact(RunPhase.REPORT, bad, Note(text="x"))


def test_missing_artifact_raises_not_found(run: Run) -> None:
    with pytest.raises(ArtifactNotFoundError):
        run.read_artifact(RunPhase.SCORING, "absent", Note)


def test_artifact_with_wrong_schema_version_is_rejected(run: Run) -> None:
    path = run.artifact_path(RunPhase.CLEANING, "old")
    path.write_text(
        '{"schema_version": "9.9", "created_at": "2026-01-01T00:00:00Z", "text": "x"}',
        encoding="utf-8",
    )
    with pytest.raises(ArtifactError, match="failed validation"):
        run.read_artifact(RunPhase.CLEANING, "old", Note)


def test_no_temp_files_left_behind(run: Run) -> None:
    run.write_artifact(RunPhase.LLM, "note", Note(text="x"))
    assert [p.name for p in (run.root / "llm").iterdir()] == ["note.json"]
