"""Discover lightweight plugin definitions without importing Runtime backends."""

import importlib
import pkgutil
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Iterable, Iterator, Sequence, Tuple

from semantic_world_v04.core.errors import PluginError
from semantic_world_v04.core.sensor_models import (
    PLUGIN_CONTRACT_VERSION,
    PluginManifest,
)


@dataclass(frozen=True)
class DiscoveredPlugin:
    kind: str
    instance: Any
    manifest: PluginManifest


class PluginLoader:
    """Scan plugin packages for declarative ``PLUGIN_CLASSES`` exports.

    Plugin definition modules must remain ordinary-Python importable. Heavy
    Kit/Isaac imports belong in runtime factory methods, never at module scope.
    """

    builtin_packages: Tuple[Tuple[str, str], ...] = (
        ("sensor", "semantic_world_v04.plugins.sensors"),
        ("modality", "semantic_world_v04.plugins.modalities"),
        ("variant", "semantic_world_v04.plugins.variants"),
    )

    def discover(self) -> Iterator[DiscoveredPlugin]:
        for kind, package_name in self.builtin_packages:
            package = importlib.import_module(package_name)
            for module in self._modules(package):
                for plugin_class in getattr(module, "PLUGIN_CLASSES", ()):
                    instance = plugin_class()
                    manifest = self._manifest(instance, kind)
                    self._validate_manifest(manifest, kind)
                    yield DiscoveredPlugin(kind, instance, manifest)

    @staticmethod
    def _modules(package: ModuleType) -> Iterable[ModuleType]:
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            return ()
        names = sorted(
            item.name
            for item in pkgutil.iter_modules(package_path)
            if not item.name.startswith("_")
        )
        return (
            importlib.import_module(f"{package.__name__}.{name}") for name in names
        )

    @staticmethod
    def _manifest(instance: Any, kind: str) -> PluginManifest:
        provider = getattr(instance, "manifest", None)
        if callable(provider):
            manifest = provider()
            if isinstance(manifest, PluginManifest):
                return manifest
            return PluginManifest.from_dict(manifest)
        attribute = "strategy_id" if kind == "variant" else "plugin_id"
        plugin_id = getattr(instance, attribute, "")
        supported: Sequence[str] = ()
        supported_method = getattr(instance, "supported_modalities", None)
        if callable(supported_method):
            supported = tuple(supported_method())
        return PluginManifest(
            plugin_id=plugin_id,
            plugin_kind=kind,
            plugin_version="1.0.0",
            display_name=plugin_id.replace("_", " ").title(),
            definition_class=(
                f"{instance.__class__.__module__}:"
                f"{instance.__class__.__qualname__}"
            ),
            supported_modalities=tuple(supported),
        )

    @staticmethod
    def _validate_manifest(manifest: PluginManifest, kind: str) -> None:
        if manifest.plugin_kind != kind:
            raise PluginError(
                f"plugin {manifest.plugin_id} declares kind "
                f"{manifest.plugin_kind}, discovered as {kind}"
            )
        if manifest.contract_version != PLUGIN_CONTRACT_VERSION:
            raise PluginError(
                f"plugin {manifest.plugin_id} uses contract version "
                f"{manifest.contract_version}; expected {PLUGIN_CONTRACT_VERSION}"
            )
