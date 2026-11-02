"""Centralized application configuration.

Precedence (highest first):
    init kwargs > environment variables (``INSIGHTOS_*``) > ``.env`` file
    > TOML config file > built-in defaults.

The TOML file is ``$INSIGHTOS_CONFIG_FILE`` when set (it must exist), otherwise the
repository's ``config/default.toml`` if present. Secrets are `SecretStr`, never belong in
TOML, and are masked by `Settings.public_dict`.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from insightos.errors import ConfigurationError

ENV_PREFIX = "INSIGHTOS_"
CONFIG_FILE_ENV_VAR = f"{ENV_PREFIX}CONFIG_FILE"
DEFAULT_CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "default.toml"

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def resolve_config_file() -> Path | None:
    """Return the TOML file to load, or None when there is none."""
    explicit = os.environ.get(CONFIG_FILE_ENV_VAR)
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            msg = f"{CONFIG_FILE_ENV_VAR} points to a missing file: {path}"
            raise ConfigurationError(msg)
        return path
    return DEFAULT_CONFIG_FILE if DEFAULT_CONFIG_FILE.is_file() else None


class Settings(BaseSettings):
    """Application settings. Immutable once constructed."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    SECRET_FIELDS: ClassVar[frozenset[str]] = frozenset({"llm_api_key"})

    # Storage and logging
    runs_dir: Path = Path("runs")
    log_level: LogLevel = "INFO"
    log_to_file: bool = True

    # LLM provider is pluggable and not finalized (Blueprint V2, section 7.5).
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # Privacy: minimum evidence only, never the full dataset, mask sensitive values.
    llm_max_samples_per_column: int = Field(default=10, ge=0)
    privacy_mask_sensitive_values: bool = True

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        config_file = resolve_config_file()
        if config_file is not None:
            _reject_unknown_keys(config_file)
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=config_file))
        return tuple(sources)

    def secret_values(self) -> list[str]:
        """Plain-text secret values, for redaction. Never log or persist the result."""
        values: list[str] = []
        for name in self.SECRET_FIELDS:
            secret = getattr(self, name)
            if isinstance(secret, SecretStr) and secret.get_secret_value():
                values.append(secret.get_secret_value())
        return values

    def public_dict(self) -> dict[str, Any]:
        """JSON-safe view of the settings with secrets replaced by ``<set>`` / ``None``."""
        data: dict[str, Any] = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if name in self.SECRET_FIELDS:
                data[name] = "<set>" if value is not None else None
            elif isinstance(value, Path):
                data[name] = str(value)
            else:
                data[name] = value
        return data


def _reject_unknown_keys(path: Path) -> None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read config file {path}: {exc}"
        raise ConfigurationError(msg) from exc
    unknown = sorted(set(data) - set(Settings.model_fields))
    if unknown:
        msg = f"unknown setting(s) in {path}: {', '.join(unknown)}"
        raise ConfigurationError(msg)
    secrets = sorted(set(data) & Settings.SECRET_FIELDS)
    if secrets:
        msg = f"secrets must not be stored in config files ({path}): {', '.join(secrets)}"
        raise ConfigurationError(msg)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings. Call ``get_settings.cache_clear()`` to reload."""
    return Settings()
