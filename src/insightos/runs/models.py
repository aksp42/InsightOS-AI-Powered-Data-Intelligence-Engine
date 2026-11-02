"""Typed contracts for the run directory (Blueprint V2 section 12)."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from insightos.schemas import InsightOSModel, VersionedArtifact


class RunPhase(StrEnum):
    """Phase subdirectories of a run, in pipeline order."""

    INPUT = "input"
    PROFILE = "profile"
    DETECTION = "detection"
    SCORING = "scoring"
    LLM = "llm"
    CLEANING = "cleaning"
    VALIDATION = "validation"
    REPORT = "report"


class InputFileRef(InsightOSModel):
    """Reference to the immutable original upload stored in ``input/``."""

    original_filename: str
    stored_path: str  # relative to the run root, always inside ``input/``
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class RunManifest(VersionedArtifact):
    """``manifest.json``: run id, InsightOS version, reference + SHA-256 of the input."""

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    run_id: str
    insightos_version: str
    input_file: InputFileRef | None = None
