"""Packaging, scaffold and repository-hygiene checks for the Phase 1 foundation."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import evaluation
import insightos
from insightos.runs import RunStore
from insightos.settings import Settings


def test_version_is_semver_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", insightos.__version__)


def test_package_is_typed(repo_root: Path) -> None:
    assert (repo_root / "src" / "insightos" / "py.typed").is_file()


def test_evaluation_scaffold_is_importable_and_empty() -> None:
    assert evaluation.__all__ == []


def test_pyproject_targets_python_311(repo_root: Path) -> None:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.11"
    assert data["tool"]["mypy"]["python_version"] == "3.11"
    assert data["tool"]["ruff"]["target-version"] == "py311"


def test_phase1_declares_no_phase2_dependencies(repo_root: Path) -> None:
    data = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    names = {re.split(r"[<>=!~ ]", dep, maxsplit=1)[0] for dep in data["project"]["dependencies"]}
    assert names == {"pydantic", "pydantic-settings"}


def test_blueprint_v2_is_present(repo_root: Path) -> None:
    assert (repo_root / "INSIGHTOS_PROJECT_BLUEPRINT_V2.md").is_file()


def test_gitignore_protects_secrets(repo_root: Path) -> None:
    lines = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    for required in (".env", ".env.*", "!.env.example", "/runs/", "__pycache__/", ".venv/"):
        assert required in lines, f".gitignore is missing {required!r}"


def test_run_store_can_be_built_from_settings(tmp_path: Path) -> None:
    store = RunStore.from_settings(Settings(runs_dir=tmp_path / "r"))
    assert store.root == tmp_path / "r"


def test_python_m_insightos_runs(repo_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "insightos", "--version"],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(repo_root / "src"), "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
    assert insightos.__version__ in result.stdout
