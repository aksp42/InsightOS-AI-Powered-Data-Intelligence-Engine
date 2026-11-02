"""Command-line entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from insightos import __version__
from insightos.cli import main
from insightos.settings import CONFIG_FILE_ENV_VAR


def test_info_prints_json_and_masks_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("INSIGHTOS_LLM_API_KEY", "sk-very-secret")
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "sk-very-secret" not in out
    payload = json.loads(out)
    assert payload["insightos_version"] == __version__
    assert payload["settings"]["llm_api_key"] == "<set>"
    assert payload["run_phase_dirs"] == [
        "input",
        "profile",
        "detection",
        "scoring",
        "llm",
        "cleaning",
        "validation",
        "report",
    ]


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: insightos" in capsys.readouterr().out


def test_bad_configuration_returns_error_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(tmp_path / "missing.toml"))
    assert main(["info"]) == 2
    assert "error:" in capsys.readouterr().err
