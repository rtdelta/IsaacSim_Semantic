"""Typed, manifest-aware plugin registry used by compiler and runtime."""

from typing import Any, Dict, Iterable, List

from semantic_world_v04.core.errors import PluginError
from semantic_world_v04.core.sensor_models import PluginManifest


class PluginRegistry:
    def __init__(self) -> None:
        self._sensors: Dict[str, Any] = {}
        self._variants: Dict[str, Any] = {}
        self._modalities: Dict[str, Any] = {}
        self._manifests: Dict[tuple, PluginManifest] = {}

    def register_sensor(
        self, plugin: Any, manifest: PluginManifest = None
    ) -> None:
        self._register(self._sensors, plugin, "sensor")
        self._remember_manifest("sensor", plugin.plugin_id, plugin, manifest)

    def register_variant(
        self, plugin: Any, manifest: PluginManifest = None
    ) -> None:
        self._register(self._variants, plugin, "variant", attribute="strategy_id")
        self._remember_manifest("variant", plugin.strategy_id, plugin, manifest)

    def register_modality(
        self, plugin: Any, manifest: PluginManifest = None
    ) -> None:
        self._register(self._modalities, plugin, "modality")
        self._remember_manifest("modality", plugin.plugin_id, plugin, manifest)

    def sensor(self, plugin_id: str) -> Any:
        return self._get(self._sensors, plugin_id, "sensor")

    def variant(self, strategy_id: str) -> Any:
        return self._get(self._variants, strategy_id, "variant")

    def modality(self, plugin_id: str) -> Any:
        return self._get(self._modalities, plugin_id, "modality")

    def sensor_ids(self) -> List[str]:
        return sorted(self._sensors)

    def variant_ids(self) -> List[str]:
        return sorted(self._variants)

    def modality_ids(self) -> List[str]:
        return sorted(self._modalities)

    def manifest(self, kind: str, plugin_id: str) -> PluginManifest:
        try:
            return self._manifests[(kind, plugin_id)]
        except KeyError as exc:
            raise PluginError(f"unknown {kind} plugin manifest: {plugin_id}") from exc

    def manifests(self, kind: str = "") -> List[PluginManifest]:
        values = [
            manifest
            for (manifest_kind, _), manifest in self._manifests.items()
            if not kind or manifest_kind == kind
        ]
        return sorted(values, key=lambda item: (item.plugin_kind, item.plugin_id))

    def _remember_manifest(
        self,
        kind: str,
        plugin_id: str,
        plugin: Any,
        manifest: PluginManifest,
    ) -> None:
        if manifest is None:
            from .loader import PluginLoader

            manifest = PluginLoader._manifest(plugin, kind)
        if manifest.plugin_id != plugin_id or manifest.plugin_kind != kind:
            raise PluginError(
                f"manifest identity mismatch for {kind} plugin {plugin_id}"
            )
        self._manifests[(kind, plugin_id)] = manifest

    @staticmethod
    def _register(
        target: Dict[str, Any],
        plugin: Any,
        kind: str,
        attribute: str = "plugin_id",
    ) -> None:
        plugin_id = getattr(plugin, attribute, None)
        if not isinstance(plugin_id, str) or not plugin_id:
            raise PluginError(f"{kind} plugin has no valid {attribute}")
        if plugin_id in target:
            raise PluginError(f"duplicate {kind} plugin id: {plugin_id}")
        target[plugin_id] = plugin

    @staticmethod
    def _get(target: Dict[str, Any], plugin_id: str, kind: str) -> Any:
        try:
            return target[plugin_id]
        except KeyError as exc:
            raise PluginError(f"unknown {kind} plugin: {plugin_id}") from exc


def build_default_registry() -> PluginRegistry:
    # Definition modules remain pure Python; runtime backends are created lazily.
    from .loader import PluginLoader

    registry = PluginRegistry()
    for discovered in PluginLoader().discover():
        if discovered.kind == "sensor":
            registry.register_sensor(discovered.instance, discovered.manifest)
        elif discovered.kind == "modality":
            registry.register_modality(discovered.instance, discovered.manifest)
        else:
            registry.register_variant(discovered.instance, discovered.manifest)
    return registry
