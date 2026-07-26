"""Temporary USD visibility isolation for the excavator-only render pass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from pxr import Sdf, Usd, UsdGeom


def _is_same_or_descendant(path: str, root: str) -> bool:
    normalized_root = root.rstrip("/")
    return path == normalized_root or path.startswith(normalized_root + "/")


def _is_ancestor_of_any(path: str, roots: Iterable[str]) -> bool:
    normalized_path = path.rstrip("/")
    return any(
        root != normalized_path and root.startswith(normalized_path + "/")
        for root in roots
    )


@dataclass(frozen=True)
class VisibilityIsolationReport:
    included_prim_paths: tuple[str, ...]
    protected_prim_paths: tuple[str, ...]
    hidden_prim_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "included_prim_paths": list(self.included_prim_paths),
            "protected_prim_paths": list(self.protected_prim_paths),
            "hidden_prim_paths": list(self.hidden_prim_paths),
        }


class SceneVisibilityController:
    """Hide excluded Imageable subtrees through a removable anonymous session layer."""

    def __init__(
        self,
        stage: Any,
        included_prim_paths: Iterable[str],
        *,
        protected_prim_paths: Iterable[str] = (),
    ) -> None:
        self._stage = stage
        self._included_paths = tuple(str(path) for path in included_prim_paths)
        self._protected_paths = tuple(str(path) for path in protected_prim_paths)
        self._session_layer = stage.GetSessionLayer()
        if self._session_layer is None:
            raise RuntimeError(
                "The opened USD Stage has no session layer for temporary visibility overrides"
            )
        self._visibility_layer = Sdf.Layer.CreateAnonymous(
            "excavator_only_visibility.usda"
        )
        self._session_layer.subLayerPaths.insert(
            0,
            self._visibility_layer.identifier,
        )
        self._active = False
        self._hidden_paths: tuple[str, ...] = ()
        self._report: VisibilityIsolationReport | None = None
        self._validate_paths()

    @property
    def active(self) -> bool:
        return self._active

    def _validate_paths(self) -> None:
        if not self._included_paths:
            raise ValueError("At least one included Prim path is required")
        for label, paths in (
            ("included", self._included_paths),
            ("protected", self._protected_paths),
        ):
            for path in paths:
                prim = self._stage.GetPrimAtPath(path)
                if not prim.IsValid():
                    raise RuntimeError(f"{label.capitalize()} Prim path does not exist: {path}")

    def _must_remain_visible(self, path: str) -> bool:
        roots = (*self._included_paths, *self._protected_paths)
        return (
            any(_is_same_or_descendant(path, root) for root in roots)
            or _is_ancestor_of_any(path, roots)
        )

    def _clear_visibility_opinions(self, paths: Iterable[str]) -> None:
        with Usd.EditContext(self._stage, self._visibility_layer):
            for path in paths:
                prim = self._stage.GetPrimAtPath(path)
                if not prim.IsValid():
                    continue
                UsdGeom.Imageable(prim).GetVisibilityAttr().Clear()

    def isolate(self) -> VisibilityIsolationReport:
        if self.active:
            raise RuntimeError("Scene visibility isolation is already active")

        hidden_paths: list[str] = []

        try:
            with Usd.EditContext(self._stage, self._visibility_layer):
                for prim in self._stage.Traverse():
                    path = str(prim.GetPath())
                    if any(_is_same_or_descendant(path, root) for root in hidden_paths):
                        continue
                    if self._must_remain_visible(path):
                        continue
                    if not prim.IsA(UsdGeom.Imageable):
                        continue
                    imageable = UsdGeom.Imageable(prim)
                    imageable.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                    hidden_paths.append(path)
        except Exception:
            self._clear_visibility_opinions(hidden_paths)
            raise

        report = VisibilityIsolationReport(
            included_prim_paths=self._included_paths,
            protected_prim_paths=self._protected_paths,
            hidden_prim_paths=tuple(hidden_paths),
        )
        self._active = True
        self._hidden_paths = report.hidden_prim_paths
        self._report = report
        return report

    def restore(self) -> None:
        if not self._active:
            return
        try:
            self._clear_visibility_opinions(self._hidden_paths)
        finally:
            self._hidden_paths = ()
            self._active = False

    def close(self) -> None:
        self.restore()
