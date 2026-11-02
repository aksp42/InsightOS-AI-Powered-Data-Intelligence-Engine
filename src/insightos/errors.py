"""Exception hierarchy. Every InsightOS-specific failure derives from `InsightOSError`."""

from __future__ import annotations


class InsightOSError(Exception):
    """Base class for all InsightOS errors."""


class ConfigurationError(InsightOSError):
    """Configuration is missing, unreadable, or invalid."""


class RunError(InsightOSError):
    """A run directory could not be created, opened, or used."""


class RunExistsError(RunError):
    """A run with the requested id already exists."""


class ImmutableInputError(RunError):
    """An attempt was made to replace the run's immutable original input."""


class ArtifactError(InsightOSError):
    """A phase artifact could not be written or read."""


class ArtifactExistsError(ArtifactError):
    """The artifact already exists and overwriting was not requested."""


class ArtifactNotFoundError(ArtifactError):
    """The requested artifact does not exist."""
