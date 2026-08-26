"""Plugin contracts and the default v04 registry."""

from .loader import PluginLoader
from .registry import PluginRegistry, build_default_registry

__all__ = ["PluginLoader", "PluginRegistry", "build_default_registry"]
