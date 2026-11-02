"""Logging configuration and secret redaction."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import SecretStr

from insightos.logging_setup import LOGGER_NAME, configure_logging, get_logger
from insightos.settings import Settings

SECRET = "sk-very-secret-123"


def _output_handlers(logger: logging.Logger) -> list[logging.Handler]:
    """Handlers that emit output (the package keeps a library-standard NullHandler too)."""
    return [h for h in logger.handlers if not isinstance(h, logging.NullHandler)]


def _flush(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        handler.flush()


def test_secrets_are_redacted_from_messages_and_tracebacks(tmp_path: Path) -> None:
    settings = Settings(llm_api_key=SecretStr(SECRET), log_level="DEBUG")
    log_file = tmp_path / "run.log"
    logger = configure_logging(settings, run_log_path=log_file)

    child = get_logger("test")
    child.info("calling provider with key %s", SECRET)
    try:
        raise RuntimeError(f"boom {SECRET}")
    except RuntimeError:
        child.exception("call failed")
    _flush(logger)

    text = log_file.read_text(encoding="utf-8")
    assert SECRET not in text
    assert "calling provider with key ***" in text
    assert "Traceback" in text
    assert "boom ***" in text


def test_configure_logging_is_idempotent(tmp_path: Path) -> None:
    settings = Settings()
    configure_logging(settings, run_log_path=tmp_path / "run.log")
    logger = configure_logging(settings, run_log_path=tmp_path / "run.log")
    assert len(_output_handlers(logger)) == 2  # stderr + file, not duplicated


def test_file_logging_can_be_disabled(tmp_path: Path) -> None:
    log_file = tmp_path / "run.log"
    logger = configure_logging(Settings(log_to_file=False), run_log_path=log_file)
    get_logger("test").warning("hello")
    _flush(logger)
    assert not log_file.exists()
    assert len(_output_handlers(logger)) == 1


def test_level_comes_from_settings() -> None:
    logger = configure_logging(Settings(log_level="ERROR"))
    assert logger.level == logging.ERROR
    assert logger.propagate is False


def test_get_logger_is_namespaced() -> None:
    assert get_logger("profiler").name == f"{LOGGER_NAME}.profiler"
    assert get_logger(f"{LOGGER_NAME}.cleaning").name == f"{LOGGER_NAME}.cleaning"
    assert get_logger(LOGGER_NAME).name == LOGGER_NAME
