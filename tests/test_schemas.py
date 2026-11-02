"""Behaviour of the shared Pydantic contract foundation."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from insightos.schemas import VersionedArtifact


class Sample(VersionedArtifact):
    SCHEMA_VERSION: ClassVar[str] = "2.1"

    value: int


def test_schema_version_is_stamped_from_class() -> None:
    assert Sample(value=1).schema_version == "2.1"


def test_created_at_is_timezone_aware() -> None:
    assert Sample(value=1).created_at.tzinfo is not None


def test_mismatched_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unsupported schema_version"):
        Sample(value=1, schema_version="1.0")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Sample(value=1, surprise=2)  # type: ignore[call-arg]


def test_models_are_immutable() -> None:
    sample = Sample(value=1)
    with pytest.raises(ValidationError):
        sample.value = 3  # type: ignore[misc]


def test_json_roundtrip_preserves_equality() -> None:
    original = Sample(value=7)
    assert Sample.model_validate_json(original.model_dump_json()) == original
