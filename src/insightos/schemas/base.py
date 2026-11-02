"""Base models for every typed contract in InsightOS.

Modules communicate through strict, immutable Pydantic models (Blueprint V2, section 5).
Persisted artifacts carry a `schema_version` (section 10) so stale files are rejected
rather than silently misread.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InsightOSModel(BaseModel):
    """Immutable model that rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class VersionedArtifact(InsightOSModel):
    """A persisted artifact. Subclasses set `SCHEMA_VERSION`; it is stamped on creation.

    Loading data whose `schema_version` differs from the class constant is an error.
    Migration between versions is deliberately not implemented yet.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def _stamp_and_check_version(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        supplied = data.get("schema_version")
        if supplied in (None, ""):
            return {**data, "schema_version": cls.SCHEMA_VERSION}
        if supplied != cls.SCHEMA_VERSION:
            msg = (
                f"unsupported schema_version {supplied!r} for {cls.__name__}; "
                f"expected {cls.SCHEMA_VERSION!r}"
            )
            raise ValueError(msg)
        return data
