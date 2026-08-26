"""Pure-Python snapshot of the subset of a USD Stage needed by v04."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from semantic_world_v04.core.errors import SchemaError


def normalize_prim_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/"):
        raise SchemaError("USD prim path must start with '/'", "prim_path")
    if path == "/":
        return path
    normalized = "/" + "/".join(part for part in path.split("/") if part)
    if normalized != path.rstrip("/"):
        raise SchemaError("USD prim path is not normalized", "prim_path")
    return normalized


def parent_prim_path(path: str) -> Optional[str]:
    normalized = normalize_prim_path(path)
    if normalized == "/":
        return None
    parent = normalized.rsplit("/", 1)[0]
    return parent or "/"


def is_same_or_descendant(path: str, ancestor: str) -> bool:
    path = normalize_prim_path(path)
    ancestor = normalize_prim_path(ancestor)
    return ancestor == "/" or path == ancestor or path.startswith(ancestor + "/")


def paths_related(left: str, right: str) -> bool:
    return is_same_or_descendant(left, right) or is_same_or_descendant(right, left)


@dataclass(frozen=True)
class PrimSummary:
    path: str
    type_name: str
    name: str = ""
    parent_path: Optional[str] = None
    visibility: str = "inherited"
    attributes: Dict[str, Any] = field(default_factory=dict)
    applied_schemas: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = normalize_prim_path(self.path)
        object.__setattr__(self, "path", normalized)
        if not self.name:
            object.__setattr__(
                self, "name", "" if normalized == "/" else normalized.rsplit("/", 1)[-1]
            )
        if self.parent_path is None:
            object.__setattr__(self, "parent_path", parent_prim_path(normalized))


class StageIndex:
    """Deterministic map of Prim paths to lightweight summaries."""

    def __init__(self, prims: Iterable[PrimSummary], stage_identifier: str = "") -> None:
        self.stage_identifier = stage_identifier
        self._prims: Dict[str, PrimSummary] = {}
        for prim in prims:
            if prim.path in self._prims:
                raise ValueError(f"duplicate prim path: {prim.path}")
            self._prims[prim.path] = prim

    def get(self, prim_path: str) -> Optional[PrimSummary]:
        return self._prims.get(normalize_prim_path(prim_path))

    def require(self, prim_path: str) -> PrimSummary:
        prim = self.get(prim_path)
        if prim is None:
            raise KeyError(prim_path)
        return prim

    def iter_prims(self) -> Iterator[PrimSummary]:
        for path in sorted(self._prims, key=lambda item: (item.count("/"), item)):
            yield self._prims[path]

    def children(self, prim_path: str) -> List[PrimSummary]:
        target = normalize_prim_path(prim_path)
        return [prim for prim in self.iter_prims() if prim.parent_path == target]

    def by_type(self, type_name: str) -> List[PrimSummary]:
        return [prim for prim in self.iter_prims() if prim.type_name == type_name]

    def search(self, text: str) -> List[PrimSummary]:
        needle = text.casefold()
        return [
            prim
            for prim in self.iter_prims()
            if needle in prim.path.casefold()
            or needle in prim.name.casefold()
            or needle in prim.type_name.casefold()
        ]

    def __len__(self) -> int:
        return len(self._prims)
