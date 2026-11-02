"""Logging with secret redaction.

Every record emitted through handlers installed here is passed through ``RedactingFormatter``,
which replaces each known secret value (from settings) with ``***`` in the final text, including
formatted exception tracebacks. Redaction applies to all non-empty secrets regardless of length.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from insightos.settings import Settings

LOGGER_NAME = "insightos"
REDACTED = "***"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MANAGED = "_insightos_managed"

# Library-standard: importing the package never prints "no handler" warnings or configures logging.
logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())


class RedactingFormatter(logging.Formatter):
    """Formatter that masks secret values in the complete formatted output."""

    def __init__(self, secrets: Iterable[str], fmt: str = _FORMAT) -> None:
        super().__init__(fmt)
        # Longest first so a secret containing another secret is fully masked.
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def format(self, record: logging.LogRecord) -> str:
        return self.redact(super().format(record))


def _secret_values(settings: Settings) -> list[str]:
    key = settings.llm_api_key
    return [key.get_secret_value()] if key is not None else []


def _mark(handler: logging.Handler) -> logging.Handler:
    setattr(handler, _MANAGED, True)
    return handler


def configure_logging(settings: Settings, run_log_path: Path | None = None) -> logging.Logger:
    """(Re)configure the ``insightos`` logger. Idempotent: no duplicate handlers."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED, False):
            logger.removeHandler(handler)
            handler.close()

    formatter = RedactingFormatter(_secret_values(settings))
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(_mark(stderr_handler))

    if settings.log_to_file and run_log_path is not None:
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(run_log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(_mark(file_handler))

    logger.setLevel(settings.log_level)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Logger namespaced under ``insightos``."""
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
