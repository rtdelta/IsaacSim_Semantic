from __future__ import annotations

from typing import Dict, TypeVar


T = TypeVar("T")


class ArtifactStore:
    """Frame-local typed artifact registry used between business modules."""

    def __init__(self) -> None:
        self._values: Dict[str, object] = {}

    def put(self, name: str, value: object) -> None:
        if name in self._values:
            raise ValueError(f"artifact already exists: {name}")
        self._values[name] = value

    def get(self, name: str, expected_type: type[T]) -> T:
        try:
            value = self._values[name]
        except KeyError as exc:
            raise KeyError(f"required artifact is missing: {name}") from exc
        if not isinstance(value, expected_type):
            raise TypeError(
                f"artifact {name!r} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        return value
