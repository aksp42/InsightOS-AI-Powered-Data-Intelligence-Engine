"""Configuration loading, precedence, and secret handling."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from insightos.errors import ConfigurationError
from insightos.settings import CONFIG_FILE_ENV_VAR, ENV_PREFIX, Settings, get_settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.runs_dir == Path("runs")
    assert settings.log_level == "INFO"
    assert settings.log_to_file is True
    assert settings.llm_provider is None
    assert settings.llm_model is None
    assert settings.llm_api_key is None
    assert settings.llm_temperature == 0.0
    assert settings.privacy_mask_sensitive_values is True


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTOS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("INSIGHTOS_RUNS_DIR", "/data/insight-runs")
    settings = Settings()
    assert settings.log_level == "DEBUG"
    assert settings.runs_dir == Path("/data/insight-runs")


def test_invalid_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTOS_LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        Settings()


def test_dotenv_file_is_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("INSIGHTOS_LLM_PROVIDER=example\n", encoding="utf-8")
    assert Settings().llm_provider == "example"


def test_empty_values_are_ignored(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("INSIGHTOS_LLM_API_KEY=\n", encoding="utf-8")
    assert Settings().llm_api_key is None


def test_environment_beats_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("INSIGHTOS_LOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.setenv("INSIGHTOS_LOG_LEVEL", "ERROR")
    assert Settings().log_level == "ERROR"


def test_toml_file_is_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "custom.toml"
    config.write_text('log_level = "WARNING"\nllm_max_samples_per_column = 3\n', encoding="utf-8")
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config))
    settings = Settings()
    assert settings.log_level == "WARNING"
    assert settings.llm_max_samples_per_column == 3


def test_environment_beats_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "custom.toml"
    config.write_text('log_level = "WARNING"\n', encoding="utf-8")
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config))
    monkeypatch.setenv("INSIGHTOS_LOG_LEVEL", "ERROR")
    assert Settings().log_level == "ERROR"


def test_missing_explicit_config_file_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(tmp_path / "does-not-exist.toml"))
    with pytest.raises(ConfigurationError):
        Settings()


def test_repo_default_toml_matches_builtin_defaults(repo_root: Path) -> None:
    data = tomllib.loads((repo_root / "config" / "default.toml").read_text(encoding="utf-8"))
    assert data, "config/default.toml should define settings"
    for key, value in data.items():
        assert key in Settings.model_fields, f"unknown setting in default.toml: {key}"
        default = Settings.model_fields[key].default
        assert type(default)(value) == default, f"default.toml drifted from code for {key}"


def test_secret_is_masked_everywhere_printable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTOS_LLM_API_KEY", "sk-very-secret")
    settings = Settings()
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-very-secret"
    assert settings.public_dict()["llm_api_key"] == "<set>"
    assert "sk-very-secret" not in json.dumps(settings.public_dict())
    assert "sk-very-secret" not in repr(settings)


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_settings()
    monkeypatch.setenv("INSIGHTOS_LOG_LEVEL", "DEBUG")
    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings().log_level == "DEBUG"


def test_env_example_only_references_known_settings(repo_root: Path) -> None:
    text = (repo_root / ".env.example").read_text(encoding="utf-8")
    names = set(re.findall(r"^#?\s*(INSIGHTOS_[A-Z_]+)=", text, flags=re.MULTILINE))
    known = {f"{ENV_PREFIX}{field.upper()}" for field in Settings.model_fields}
    known.add(CONFIG_FILE_ENV_VAR)
    assert names, ".env.example should list variables"
    assert names <= known, f"unknown variables in .env.example: {names - known}"


def test_env_example_contains_no_secret_values(repo_root: Path) -> None:
    text = (repo_root / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("INSIGHTOS_LLM_API_KEY="):
            assert line == "INSIGHTOS_LLM_API_KEY="
