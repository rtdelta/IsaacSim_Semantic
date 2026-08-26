"""Session-layer scene isolation and explicit visibility for capture variants."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .config import VariantConfig


def _is_same_or_descendant(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def select_isolation_paths(
    imageable_paths: Iterable[str], keep_paths: Iterable[str]
) -> tuple[str, ...]:
    """Return shallowest Imageable roots wholly outside every kept branch."""

    kept = tuple(dict.fromkeys(keep_paths))
    selected: list[str] = []
    candidates = sorted(set(imageable_paths), key=lambda item: (item.count("/"), item))
    for path in candidates:
        if any(
            _is_same_or_descendant(path, keep)
            or _is_same_or_descendant(keep, path)
            for keep in kept
        ):
            continue
        if any(_is_same_or_descendant(path, parent) for parent in selected):
            continue
        selected.append(path)
    return tuple(selected)


class VariantController:
    """Apply capture variants exclusively through the USD session layer."""

    def __init__(
        self,
        stage: Any,
        variants: tuple[VariantConfig, ...],
        *,
        protected_paths: Iterable[str] = (),
    ) -> None:
        from pxr import UsdGeom

        self.stage = stage
        self.variants = {item.variant_id: item for item in variants}
        self.protected_paths = tuple(dict.fromkeys(protected_paths))
        prims_by_path = {
            str(prim.GetPath()): prim
            for prim in stage.Traverse()
            if prim is not None and prim.IsValid()
        }
        imageable_paths = tuple(
            path for path, prim in prims_by_path.items() if prim.IsA(UsdGeom.Imageable)
        )
        self.isolation_paths: dict[str, tuple[str, ...]] = {}
        for variant in variants:
            for path in variant.include_paths:
                if path not in prims_by_path:
                    raise ValueError(f"Variant include prim does not exist: {path}")
            # Explicit inherited paths are intentional whitelist exceptions.  A
            # hidden ancestor would otherwise make that explicit opinion useless.
            explicit_visible = tuple(
                path for path, state in variant.visibility.items() if state == "inherited"
            )
            keep = (*variant.include_paths, *self.protected_paths, *explicit_visible)
            self.isolation_paths[variant.variant_id] = (
                select_isolation_paths(imageable_paths, keep)
                if variant.include_paths
                else ()
            )
        self.controlled_paths = sorted({
            path
            for variant in variants
            for path in (*variant.visibility, *self.isolation_paths[variant.variant_id])
        })
        self.baseline: dict[str, str] = {}
        for path in self.controlled_paths:
            prim = stage.GetPrimAtPath(path)
            if prim is None or not prim.IsValid():
                raise ValueError(f"Variant visibility prim does not exist: {path}")
            imageable = UsdGeom.Imageable(prim)
            if not imageable:
                raise ValueError(f"Variant visibility prim is not Imageable: {path}")
            value = imageable.GetVisibilityAttr().Get()
            self.baseline[path] = str(value or "inherited")
        self.current: str | None = None

    def apply(self, variant_id: str) -> None:
        from pxr import UsdGeom

        variant = self.variants[variant_id]
        isolated = set(self.isolation_paths[variant_id])
        session = self.stage.GetSessionLayer()
        previous = self.stage.GetEditTarget()
        self.stage.SetEditTarget(session)
        try:
            for path in self.controlled_paths:
                prim = self.stage.GetPrimAtPath(path)
                if prim is None or not prim.IsValid():
                    raise ValueError(f"Variant visibility prim does not exist: {path}")
                state = self.baseline[path]
                if path in isolated:
                    state = "invisible"
                if path in variant.visibility:
                    state = variant.visibility[path]
                UsdGeom.Imageable(prim).GetVisibilityAttr().Set(state)
        finally:
            self.stage.SetEditTarget(previous)
        self.current = variant_id


def reset_render_history() -> None:
    """Reset PathTracing accumulation after a visibility transition."""

    try:
        import carb.settings

        settings = carb.settings.get_settings()
        path = "/rtx/externalFrameCounter"
        current = int(settings.get(path) or 0)
        settings.set_int(path, current + 1)
    except Exception:
        return
