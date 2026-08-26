"""Atomic USD visibility switching for all render variants in one process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from pxr import Sdf, Usd, UsdGeom

from capture_context import CaptureVariant


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
    """Compatibility report for one isolated visibility state."""

    included_prim_paths: tuple[str, ...]
    protected_prim_paths: tuple[str, ...]
    hidden_prim_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "included_prim_paths": list(self.included_prim_paths),
            "protected_prim_paths": list(self.protected_prim_paths),
            "hidden_prim_paths": list(self.hidden_prim_paths),
        }


@dataclass(frozen=True)
class SceneVariantTransitionReport:
    """Auditable result of one completed visibility transition."""

    variant: CaptureVariant
    visibility_generation: int
    included_prim_paths: tuple[str, ...]
    protected_prim_paths: tuple[str, ...]
    hidden_prim_paths: tuple[str, ...]
    validation_errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.validation_errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_variant": self.variant.value,
            "visibility_generation": int(self.visibility_generation),
            "included_prim_paths": list(self.included_prim_paths),
            "protected_prim_paths": list(self.protected_prim_paths),
            "hidden_prim_paths": list(self.hidden_prim_paths),
            "validation_errors": list(self.validation_errors),
            "valid": self.valid,
        }


@dataclass(frozen=True)
class FullSceneVisibilityEntry:
    """Read-only composed visibility captured before variant isolation starts."""

    prim_path: str
    has_authored_value: bool
    composed_value: str
    effective_visibility: str


@dataclass(frozen=True)
class PersistentLayerState:
    """Initial in-memory state of one non-anonymous USD layer."""

    identifier: str
    real_path: str
    dirty: bool


class SceneVariantController:
    """Switch explicit values in one anonymous layer without editing persistent USD."""

    def __init__(
        self,
        stage: Any,
        variant_prim_paths: Mapping[CaptureVariant | str, Iterable[str]],
        *,
        protected_prim_paths: Iterable[str] = (),
        layer_name: str = "semantic_capture_visibility.usda",
        stage_update_callback: Callable[[], None] | None = None,
    ) -> None:
        self._stage = stage
        self._protected_paths = tuple(str(path) for path in protected_prim_paths)
        self._variant_paths: dict[CaptureVariant, tuple[str, ...]] = {
            CaptureVariant.FULL_SCENE: (),
        }
        for raw_variant, paths in variant_prim_paths.items():
            variant = CaptureVariant(raw_variant)
            normalized = tuple(str(path) for path in paths)
            if variant is CaptureVariant.FULL_SCENE and normalized:
                raise ValueError("FULL_SCENE must not define an isolated Prim whitelist")
            if variant is not CaptureVariant.FULL_SCENE and not normalized:
                raise ValueError(f"{variant.value} requires at least one included Prim path")
            self._variant_paths[variant] = normalized

        self._session_layer = stage.GetSessionLayer()
        if self._session_layer is None:
            raise RuntimeError(
                "The opened USD Stage has no session layer for temporary visibility overrides"
            )
        if not isinstance(layer_name, str) or not layer_name.strip():
            raise ValueError("layer_name must be a non-empty string")
        if stage_update_callback is not None and not callable(stage_update_callback):
            raise TypeError("stage_update_callback must be callable or None")
        self._stage_update_callback = stage_update_callback

        # Keep every subsequent runtime authoring operation in the anonymous
        # Session Layer.  Persistent root/sublayers are never selected as the
        # Stage edit target by this capture pipeline.
        self._stage.SetEditTarget(Usd.EditTarget(self._session_layer))
        self._persistent_layers = self._snapshot_persistent_layers()

        self._validate_paths()
        self._hidden_by_variant = {
            variant: self._calculate_hidden_paths(included_paths)
            for variant, included_paths in self._variant_paths.items()
        }
        self._full_scene_snapshot = self._snapshot_full_scene_visibility()
        self._managed_paths = tuple(
            sorted(
                {
                    path
                    for variant, hidden_paths in self._hidden_by_variant.items()
                    if variant is not CaptureVariant.FULL_SCENE
                    for path in hidden_paths
                }
            )
        )
        self._variant_visibility_values = self._build_variant_visibility_values()
        self._visibility_layer = Sdf.Layer.CreateAnonymous(layer_name.strip())
        self._visibility_specs = self._create_visibility_override_specs()
        self._session_layer.subLayerPaths.insert(
            0,
            self._visibility_layer.identifier,
        )
        self._write_variant_values(CaptureVariant.FULL_SCENE)
        if self._stage_update_callback is not None:
            self._stage_update_callback()
        self._current_variant = CaptureVariant.FULL_SCENE
        self._visibility_generation = 0
        self._last_report = self._make_report(CaptureVariant.FULL_SCENE, ())
        self.assert_persistent_layers_pristine()

    @property
    def current_variant(self) -> CaptureVariant:
        return self._current_variant

    @property
    def visibility_generation(self) -> int:
        return self._visibility_generation

    @property
    def last_report(self) -> SceneVariantTransitionReport:
        return self._last_report

    @property
    def available_variants(self) -> tuple[CaptureVariant, ...]:
        return tuple(self._variant_paths)

    @property
    def active_layer_identifier(self) -> str:
        return self._visibility_layer.identifier

    def protection_report(self) -> dict[str, Any]:
        return {
            "edit_target": str(self._stage.GetEditTarget().GetLayer().identifier),
            "session_layer": str(self._session_layer.identifier),
            "persistent_layers": [
                {
                    "identifier": state.identifier,
                    "real_path": state.real_path,
                    "initial_dirty": state.dirty,
                }
                for state in self._persistent_layers.values()
            ],
            "full_scene_visibility_entries": len(self._full_scene_snapshot),
            "visibility_override_layer": self._visibility_layer.identifier,
            "visibility_override_layer_anonymous": bool(
                getattr(self._visibility_layer, "anonymous", False)
            ),
            "managed_visibility_paths": len(self._managed_paths),
            "strategy": "persistent_anonymous_explicit_values",
        }

    @staticmethod
    def _layer_dirty(layer: Any) -> bool:
        return bool(getattr(layer, "dirty", False))

    def _snapshot_persistent_layers(self) -> dict[str, PersistentLayerState]:
        states: dict[str, PersistentLayerState] = {}
        for layer in self._stage.GetLayerStack(includeSessionLayers=False):
            if bool(getattr(layer, "anonymous", False)):
                continue
            identifier = str(layer.identifier)
            states[identifier] = PersistentLayerState(
                identifier=identifier,
                real_path=str(getattr(layer, "realPath", "") or ""),
                dirty=self._layer_dirty(layer),
            )
        return states

    def assert_persistent_layers_pristine(self) -> None:
        errors: list[str] = []
        edit_layer = self._stage.GetEditTarget().GetLayer()
        if edit_layer != self._session_layer:
            errors.append(
                "Stage edit target escaped the anonymous Session Layer: "
                f"{edit_layer.identifier}"
            )
        current_layers = {
            str(layer.identifier): layer
            for layer in self._stage.GetLayerStack(includeSessionLayers=False)
            if not bool(getattr(layer, "anonymous", False))
        }
        for identifier, initial in self._persistent_layers.items():
            layer = current_layers.get(identifier)
            if layer is None:
                errors.append(f"persistent layer left the layer stack: {identifier}")
                continue
            current_dirty = self._layer_dirty(layer)
            if current_dirty != initial.dirty:
                errors.append(
                    f"persistent layer dirty state changed: {identifier} "
                    f"({initial.dirty} -> {current_dirty})"
                )
        for identifier, layer in current_layers.items():
            if identifier not in self._persistent_layers and self._layer_dirty(layer):
                errors.append(f"new persistent layer is dirty: {identifier}")
        if errors:
            raise RuntimeError(
                "Persistent USD layer protection failed: " + "; ".join(errors)
            )

    def _snapshot_full_scene_visibility(
        self,
    ) -> dict[str, FullSceneVisibilityEntry]:
        snapshot: dict[str, FullSceneVisibilityEntry] = {}
        for prim in self._stage.Traverse():
            if not prim.IsA(UsdGeom.Imageable):
                continue
            imageable = UsdGeom.Imageable(prim)
            visibility = imageable.GetVisibilityAttr()
            value = visibility.Get(Usd.TimeCode.Default())
            path = str(prim.GetPath())
            snapshot[path] = FullSceneVisibilityEntry(
                prim_path=path,
                has_authored_value=bool(visibility.HasAuthoredValueOpinion()),
                composed_value=str(value) if value is not None else "",
                effective_visibility=str(
                    imageable.ComputeVisibility(Usd.TimeCode.Default())
                ),
            )
        return snapshot

    def _build_variant_visibility_values(
        self,
    ) -> dict[CaptureVariant, dict[str, str]]:
        baseline = {
            path: (
                self._full_scene_snapshot[path].composed_value
                or str(UsdGeom.Tokens.inherited)
            )
            for path in self._managed_paths
        }
        values: dict[CaptureVariant, dict[str, str]] = {}
        for variant in self._variant_paths:
            variant_values = dict(baseline)
            for path in self._hidden_by_variant[variant]:
                variant_values[path] = str(UsdGeom.Tokens.invisible)
            values[variant] = variant_values
        return values

    def _create_visibility_override_specs(self) -> dict[str, Any]:
        specs: dict[str, Any] = {}
        for path in self._managed_paths:
            prim_spec = Sdf.CreatePrimInLayer(
                self._visibility_layer,
                Sdf.Path(path),
            )
            specs[path] = Sdf.AttributeSpec(
                prim_spec,
                "visibility",
                Sdf.ValueTypeNames.Token,
                Sdf.VariabilityVarying,
            )
        return specs

    def _write_variant_values(self, variant: CaptureVariant) -> None:
        values = self._variant_visibility_values[variant]
        with Sdf.ChangeBlock():
            for path, value in values.items():
                self._visibility_specs[path].default = value

    def _pulse_variant_for(self, target: CaptureVariant) -> CaptureVariant:
        if target is not CaptureVariant.FULL_SCENE:
            return CaptureVariant.FULL_SCENE
        isolated = [
            variant
            for variant in self._variant_paths
            if variant is not CaptureVariant.FULL_SCENE
        ]
        if not isolated:
            return CaptureVariant.FULL_SCENE
        return max(
            isolated,
            key=lambda variant: len(self._hidden_by_variant[variant]),
        )

    def _apply_variant_values(
        self,
        variant: CaptureVariant,
        *,
        force_pulse: bool,
    ) -> None:
        if force_pulse:
            pulse_variant = self._pulse_variant_for(variant)
            self._write_variant_values(pulse_variant)
            if self._stage_update_callback is not None:
                self._stage_update_callback()
        self._write_variant_values(variant)
        if self._stage_update_callback is not None:
            self._stage_update_callback()

    def _validate_paths(self) -> None:
        for label, paths in (
            ("protected", self._protected_paths),
            *(
                (variant.value, paths)
                for variant, paths in self._variant_paths.items()
                if variant is not CaptureVariant.FULL_SCENE
            ),
        ):
            for path in paths:
                prim = self._stage.GetPrimAtPath(path)
                if not prim.IsValid():
                    raise RuntimeError(f"{label.capitalize()} Prim path does not exist: {path}")

    def _must_remain_visible(self, path: str, included_paths: tuple[str, ...]) -> bool:
        roots = (*included_paths, *self._protected_paths)
        return (
            any(_is_same_or_descendant(path, root) for root in roots)
            or _is_ancestor_of_any(path, roots)
        )

    def _calculate_hidden_paths(
        self,
        included_paths: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not included_paths:
            return ()
        hidden_paths: list[str] = []
        for prim in self._stage.Traverse():
            path = str(prim.GetPath())
            if any(_is_same_or_descendant(path, root) for root in hidden_paths):
                continue
            if self._must_remain_visible(path, included_paths):
                continue
            if not prim.IsA(UsdGeom.Imageable):
                continue
            hidden_paths.append(path)
        return tuple(hidden_paths)

    def _state_validation_errors(self, variant: CaptureVariant) -> tuple[str, ...]:
        errors: list[str] = []
        hidden_paths = self._hidden_by_variant[variant]
        for path in hidden_paths:
            prim = self._stage.GetPrimAtPath(path)
            if not prim.IsValid():
                errors.append(f"hidden Prim is missing: {path}")
                continue
            if UsdGeom.Imageable(prim).ComputeVisibility() != UsdGeom.Tokens.invisible:
                errors.append(f"hidden Prim remains effectively visible: {path}")

        roots = (*self._variant_paths[variant], *self._protected_paths)
        for path in roots:
            prim = self._stage.GetPrimAtPath(path)
            if not prim.IsValid():
                errors.append(f"required Prim is missing: {path}")
                continue
            if (
                prim.IsA(UsdGeom.Imageable)
                and UsdGeom.Imageable(prim).ComputeVisibility()
                == UsdGeom.Tokens.invisible
            ):
                errors.append(f"required Prim is effectively invisible: {path}")
        if variant is CaptureVariant.FULL_SCENE:
            for path, baseline in self._full_scene_snapshot.items():
                prim = self._stage.GetPrimAtPath(path)
                if not prim.IsValid() or not prim.IsA(UsdGeom.Imageable):
                    errors.append(f"full-scene baseline Prim is missing: {path}")
                    continue
                imageable = UsdGeom.Imageable(prim)
                visibility = imageable.GetVisibilityAttr()
                value = visibility.Get(Usd.TimeCode.Default())
                current_composed = str(value) if value is not None else ""
                current_effective = str(
                    imageable.ComputeVisibility(Usd.TimeCode.Default())
                )
                if (
                    current_composed != baseline.composed_value
                    or current_effective != baseline.effective_visibility
                ):
                    errors.append(
                        "full-scene visibility differs from startup baseline: "
                        f"{path}"
                    )
        return tuple(errors)

    def _make_report(
        self,
        variant: CaptureVariant,
        errors: tuple[str, ...],
        *,
        generation: int | None = None,
    ) -> SceneVariantTransitionReport:
        return SceneVariantTransitionReport(
            variant=variant,
            visibility_generation=(
                self._visibility_generation if generation is None else generation
            ),
            included_prim_paths=self._variant_paths[variant],
            protected_prim_paths=self._protected_paths,
            hidden_prim_paths=self._hidden_by_variant.get(variant, ()),
            validation_errors=errors,
        )

    def assert_state(
        self,
        expected_variant: CaptureVariant,
        *,
        expected_generation: int | None = None,
    ) -> SceneVariantTransitionReport:
        expected_variant = CaptureVariant(expected_variant)
        self.assert_persistent_layers_pristine()
        if self._current_variant is not expected_variant:
            raise RuntimeError(
                f"Scene variant is {self._current_variant.value}; "
                f"expected {expected_variant.value}"
            )
        if (
            expected_generation is not None
            and self._visibility_generation != expected_generation
        ):
            raise RuntimeError(
                f"Visibility generation is {self._visibility_generation}; "
                f"expected {expected_generation}"
            )
        errors = self._state_validation_errors(expected_variant)
        report = self._make_report(expected_variant, errors)
        if errors:
            raise RuntimeError(
                f"Scene variant {expected_variant.value} failed USD visibility validation: "
                + "; ".join(errors)
            )
        self._last_report = report
        return report

    def transition_to(
        self,
        target_variant: CaptureVariant,
        *,
        force_reapply: bool = False,
    ) -> SceneVariantTransitionReport:
        target_variant = CaptureVariant(target_variant)
        if target_variant not in self._variant_paths:
            raise RuntimeError(f"Scene variant is not configured: {target_variant.value}")
        self.assert_persistent_layers_pristine()
        if target_variant is self._current_variant and not force_reapply:
            return self.assert_state(target_variant)

        previous_variant = self._current_variant
        try:
            self._apply_variant_values(
                target_variant,
                force_pulse=force_reapply,
            )
            errors = self._state_validation_errors(target_variant)
            if errors:
                raise RuntimeError("; ".join(errors))
        except Exception:
            self._apply_variant_values(previous_variant, force_pulse=True)
            raise

        next_generation = self._visibility_generation + 1
        self._current_variant = target_variant
        self._visibility_generation = next_generation
        self._last_report = self._make_report(
            target_variant,
            (),
            generation=next_generation,
        )
        self.assert_persistent_layers_pristine()
        return self._last_report

    def force_reapply(
        self,
        target_variant: CaptureVariant,
    ) -> SceneVariantTransitionReport:
        return self.transition_to(target_variant, force_reapply=True)

    def restore_full_scene(self) -> SceneVariantTransitionReport:
        return self.transition_to(CaptureVariant.FULL_SCENE)

    def close(self) -> None:
        self._write_variant_values(CaptureVariant.FULL_SCENE)
        if self._stage_update_callback is not None:
            self._stage_update_callback()
        self._current_variant = CaptureVariant.FULL_SCENE
        errors = self._state_validation_errors(CaptureVariant.FULL_SCENE)
        if errors:
            raise RuntimeError(
                "Full scene did not return to its startup visibility baseline: "
                + "; ".join(errors)
            )
        with Sdf.ChangeBlock():
            identifier = self._visibility_layer.identifier
            while identifier in self._session_layer.subLayerPaths:
                self._session_layer.subLayerPaths.remove(identifier)
        if self._stage_update_callback is not None:
            self._stage_update_callback()
        errors = self._state_validation_errors(CaptureVariant.FULL_SCENE)
        if errors:
            raise RuntimeError(
                "Removing the anonymous visibility layer changed the original "
                "full-scene baseline: " + "; ".join(errors)
            )
        self.assert_persistent_layers_pristine()


class SceneVisibilityController:
    """Compatibility adapter for callers that still use isolate()/restore()."""

    def __init__(
        self,
        stage: Any,
        included_prim_paths: Iterable[str],
        *,
        protected_prim_paths: Iterable[str] = (),
        layer_name: str = "isolated_render_visibility.usda",
    ) -> None:
        self._controller = SceneVariantController(
            stage=stage,
            variant_prim_paths={
                CaptureVariant.EXCAVATOR_ONLY: tuple(included_prim_paths),
            },
            protected_prim_paths=protected_prim_paths,
            layer_name=layer_name,
        )

    @property
    def active(self) -> bool:
        return self._controller.current_variant is not CaptureVariant.FULL_SCENE

    def isolate(self) -> VisibilityIsolationReport:
        if self.active:
            raise RuntimeError("Scene visibility isolation is already active")
        report = self._controller.transition_to(CaptureVariant.EXCAVATOR_ONLY)
        return VisibilityIsolationReport(
            included_prim_paths=report.included_prim_paths,
            protected_prim_paths=report.protected_prim_paths,
            hidden_prim_paths=report.hidden_prim_paths,
        )

    def restore(self) -> None:
        self._controller.restore_full_scene()

    def close(self) -> None:
        self._controller.close()
