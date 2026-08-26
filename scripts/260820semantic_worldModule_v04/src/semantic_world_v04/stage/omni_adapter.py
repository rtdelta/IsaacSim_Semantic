"""Omniverse USD adapter.

This module intentionally performs no omni/pxr import at module import time so
the core package remains usable on the Windows development machine.
"""

import asyncio
from typing import Any, Dict, Iterable, List, Optional

from semantic_world_v04.plugins.variants import VisibilityPlan

from .index import PrimSummary, StageIndex


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    get_row = getattr(value, "GetRow", None)
    if callable(get_row):
        try:
            rows = [get_row(index) for index in range(4)]
            if all(len(row) == 4 for row in rows):
                return [[_jsonable(number) for number in row] for row in rows]
        except (IndexError, TypeError):
            pass
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__iter__"):
        try:
            return [_jsonable(item) for item in value]
        except TypeError:
            pass
    return str(value)


def read_camera_parameters(stage: Any, prim_path: str) -> Dict[str, Any]:
    """Read the effective composed USD Camera values at the default time."""

    from pxr import Usd, UsdGeom  # type: ignore

    prim = stage.GetPrimAtPath(prim_path)
    if prim is None or not prim.IsValid() or str(prim.GetTypeName()) != "Camera":
        raise ValueError(f"camera Prim does not exist: {prim_path}")
    camera = UsdGeom.Camera(prim)
    camera_attrs = {
        "focalLength": camera.GetFocalLengthAttr(),
        "horizontalAperture": camera.GetHorizontalApertureAttr(),
        "verticalAperture": camera.GetVerticalApertureAttr(),
        "horizontalApertureOffset": camera.GetHorizontalApertureOffsetAttr(),
        "verticalApertureOffset": camera.GetVerticalApertureOffsetAttr(),
        "clippingRange": camera.GetClippingRangeAttr(),
        "focusDistance": camera.GetFocusDistanceAttr(),
        "fStop": camera.GetFStopAttr(),
        "projection": camera.GetProjectionAttr(),
    }
    result: Dict[str, Any] = {}
    for name, attribute in camera_attrs.items():
        value = attribute.Get(Usd.TimeCode.Default())
        if value is not None:
            result[name] = _jsonable(value)
    xformable = UsdGeom.Xformable(prim)
    if xformable:
        result["transform"] = _jsonable(
            xformable.GetLocalTransformation(Usd.TimeCode.Default())
        )
        result["worldTransform"] = _jsonable(
            xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        )
    return result


def read_sensor_attributes(stage: Any, prim_path: str) -> Dict[str, Any]:
    """Read authored/composed sensor attributes without assuming one schema."""

    from pxr import Usd  # type: ignore

    prim = stage.GetPrimAtPath(prim_path)
    if prim is None or not prim.IsValid():
        raise ValueError(f"sensor Prim does not exist: {prim_path}")
    terms = (
        "fisheye",
        "ftheta",
        "lens",
        "distortion",
        "projection",
        "lidar",
        "sensor",
        "scan",
        "range",
        "azimuth",
        "elevation",
        "rotation",
    )
    result: Dict[str, Any] = {}
    for attribute in prim.GetAttributes():
        name = str(attribute.GetName())
        if not any(term in name.casefold() for term in terms):
            continue
        value = attribute.Get(Usd.TimeCode.Default())
        if value is not None:
            result[name] = _jsonable(value)
    result["typeName"] = str(prim.GetTypeName())
    result["appliedSchemas"] = [str(item) for item in prim.GetAppliedSchemas()]
    return result


def read_fisheye_parameters(stage: Any, prim_path: str) -> Dict[str, Any]:
    result = read_camera_parameters(stage, prim_path)
    result.update(read_sensor_attributes(stage, prim_path))
    return result


def build_stage_index(stage: Any) -> StageIndex:
    """Create a USD-neutral StageIndex from a pxr.Usd.Stage."""

    from pxr import Usd, UsdGeom  # type: ignore

    prims: List[PrimSummary] = [
        PrimSummary("/", "PseudoRoot", name="", parent_path=None)
    ]
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        type_name = str(prim.GetTypeName())
        attributes: Dict[str, Any] = {}
        visibility = "inherited"

        imageable = UsdGeom.Imageable(prim)
        if imageable:
            visibility_value = imageable.GetVisibilityAttr().Get(Usd.TimeCode.Default())
            if visibility_value is not None:
                visibility = str(visibility_value)

        if type_name == "Camera":
            attributes.update(read_camera_parameters(stage, path))

        sensor_attribute_terms = (
            "semantic",
            "fisheye",
            "ftheta",
            "lens",
            "distortion",
            "projection",
            "lidar",
            "sensor",
            "scan",
            "range",
            "azimuth",
            "elevation",
            "rotation",
        )
        for attribute in prim.GetAttributes():
            name = attribute.GetName()
            folded = name.casefold()
            if any(term in folded for term in sensor_attribute_terms):
                value = attribute.Get(Usd.TimeCode.Default())
                if value is not None:
                    attributes[name] = _jsonable(value)

        prims.append(
            PrimSummary(
                path=path,
                type_name=type_name,
                name=prim.GetName(),
                visibility=visibility,
                attributes=attributes,
                applied_schemas=tuple(str(item) for item in prim.GetAppliedSchemas()),
            )
        )
    root_layer = stage.GetRootLayer()
    return StageIndex(prims, stage_identifier=str(root_layer.identifier))


class OmniStageService:
    """Open a Stage in the current omni.usd context and produce an index."""

    def __init__(self) -> None:
        self._stage = None
        self._index: Optional[StageIndex] = None

    @property
    def stage(self) -> Any:
        return self._stage

    @property
    def index(self) -> Optional[StageIndex]:
        return self._index

    async def open(self, usd_path: str, timeout_seconds: float = 300.0) -> StageIndex:
        import omni.kit.app  # type: ignore
        import omni.usd  # type: ignore

        context = omni.usd.get_context()
        context.disable_save_to_recent_files()
        try:
            success, error = await context.open_stage_async(usd_path)
        finally:
            context.enable_save_to_recent_files()
        if not success:
            raise RuntimeError(f"failed to open USD Stage {usd_path}: {error}")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while context.get_stage_loading_status()[2] > 0:
            if loop.time() >= deadline:
                raise TimeoutError(f"timed out loading USD Stage: {usd_path}")
            await omni.kit.app.get_app().next_update_async()

        stage = context.get_stage()
        if stage is None:
            raise RuntimeError(f"USD context returned no Stage after opening {usd_path}")
        self._stage = stage
        self._index = build_stage_index(stage)
        return self._index

    def rebuild_index(self) -> StageIndex:
        if self._stage is None:
            raise RuntimeError("no Stage is open")
        self._index = build_stage_index(self._stage)
        return self._index

    def close(self) -> None:
        """Close the current Stage and discard its lightweight index."""

        import omni.usd  # type: ignore

        omni.usd.get_context().close_stage()
        self._stage = None
        self._index = None


class SessionVisibilityController:
    """Own a disposable anonymous sublayer for one v04 visibility plan."""

    def __init__(self, stage: Any) -> None:
        self._stage = stage
        self._layer = None

    def apply(self, plan: VisibilityPlan) -> None:
        from pxr import Sdf, UsdGeom  # type: ignore

        self.clear()
        session_layer = self._stage.GetSessionLayer()
        if self._layer is None:
            self._layer = Sdf.Layer.CreateAnonymous(
                "semantic_world_v04_variant.usda"
            )
            paths = list(session_layer.subLayerPaths)
            if self._layer.identifier not in paths:
                paths.insert(0, self._layer.identifier)
                session_layer.subLayerPaths = paths
        layer = self._layer
        previous_target = self._stage.GetEditTarget()
        try:
            self._stage.SetEditTarget(layer)
            for path in plan.hidden_roots:
                prim = self._stage.GetPrimAtPath(path)
                if prim and prim.IsValid():
                    imageable = UsdGeom.Imageable(prim)
                    if imageable:
                        imageable.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            for path in self._expanded_protected_paths(plan.protected_paths):
                prim = self._stage.GetPrimAtPath(path)
                if prim and prim.IsValid():
                    imageable = UsdGeom.Imageable(prim)
                    if imageable:
                        imageable.CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
        finally:
            self._stage.SetEditTarget(previous_target)

    def clear(self) -> None:
        if self._layer is None:
            return
        # Keep the anonymous layer registered and strongly referenced for the
        # lifetime of the Stage. Removing it while Hydra/Replicator consumes
        # notices can leave a NULL TfWeakPtr<SdfLayer> in Kit 110.1.
        self._layer.Clear()

    @staticmethod
    def _ancestor_paths(path: str) -> Iterable[str]:
        parts = [part for part in path.split("/") if part]
        for index in range(1, len(parts) + 1):
            yield "/" + "/".join(parts[:index])

    def _expanded_protected_paths(self, paths: Iterable[str]) -> List[str]:
        expanded = set()
        for path in paths:
            expanded.update(self._ancestor_paths(path))
        return sorted(expanded, key=lambda value: (value.count("/"), value))


class SessionSensorOverrideController:
    """Own a disposable anonymous layer for sensor parameter overrides."""

    def __init__(self, stage: Any) -> None:
        self._stage = stage
        self._layer = None

    def apply(self, sensor: Any, plugin: Any) -> Dict[str, Any]:
        from pxr import Sdf  # type: ignore

        if self._layer is None:
            self._layer = Sdf.Layer.CreateAnonymous(
                "semantic_world_v04_sensor_overrides.usda"
            )
            session_layer = self._stage.GetSessionLayer()
            paths = list(session_layer.subLayerPaths)
            if self._layer.identifier not in paths:
                paths.insert(0, self._layer.identifier)
                session_layer.subLayerPaths = paths
        previous_target = self._stage.GetEditTarget()
        try:
            self._stage.SetEditTarget(self._layer)
            return dict(plugin.author_runtime_overrides(self._stage, sensor))
        finally:
            self._stage.SetEditTarget(previous_target)

    def clear(self) -> None:
        if self._layer is not None:
            # Retain the anonymous layer while Hydra can still process notices.
            self._layer.Clear()
