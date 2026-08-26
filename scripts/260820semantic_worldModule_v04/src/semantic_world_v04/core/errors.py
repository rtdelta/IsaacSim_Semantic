"""Structured errors shared by the editor, compiler, supervisor, and runtime."""

from typing import Iterable, List, Optional


class SemanticWorldError(Exception):
    """Base class for expected v04 errors."""


class SchemaError(SemanticWorldError):
    """Raised when a serialized project or job violates its schema."""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class ProjectIOError(SemanticWorldError):
    """Raised when a project cannot be read or atomically persisted."""


class PluginError(SemanticWorldError):
    """Raised for plugin registration or lookup failures."""


class JobStateError(SemanticWorldError):
    """Raised when a supervisor lifecycle transition is invalid."""


class RuntimeBootstrapError(SemanticWorldError):
    """Raised before capture when the Isaac/Kit environment is invalid."""


class ValidationFailed(SemanticWorldError):
    """Raised when one or more structured validation issues block execution."""

    def __init__(self, issues: Iterable["ValidationIssueLike"]) -> None:
        self.issues: List["ValidationIssueLike"] = list(issues)
        super().__init__(
            "validation failed: " + "; ".join(str(issue) for issue in self.issues)
        )


class ValidationIssueLike:
    """Narrow structural type used to avoid a circular models import."""

    code: str
    message: str
    path: str
    hint: Optional[str]

