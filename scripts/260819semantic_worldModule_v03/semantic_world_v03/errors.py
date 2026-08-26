"""Project-specific exceptions with stable failure categories."""

from __future__ import annotations


class SemanticWorldError(RuntimeError):
    """Base class for expected v03 runtime failures."""


class ConfigurationError(SemanticWorldError, ValueError):
    """The run configuration is invalid before Isaac Sim starts."""


class PreflightError(SemanticWorldError):
    """A loaded USD stage or configured sensor cannot be used."""


class SensorStateError(SemanticWorldError):
    """A sensor driver lifecycle operation was called out of order."""


class SensorCaptureError(SemanticWorldError):
    """A sensor did not produce a valid sample."""


class TransactionError(SemanticWorldError):
    """Staged outputs could not be validated or atomically committed."""


class ResumeError(SemanticWorldError):
    """Existing output is incompatible with the requested resumed run."""


class WorkerTimeoutError(SemanticWorldError):
    """The out-of-process worker heartbeat exceeded its phase timeout."""


class WorkerTerminationError(SemanticWorldError):
    """A stale worker remained alive after terminate and kill attempts."""
