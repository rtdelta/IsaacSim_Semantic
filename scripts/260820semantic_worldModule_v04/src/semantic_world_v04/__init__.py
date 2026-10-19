"""Semantic World Module v04.

The top-level package deliberately imports only pure-Python modules. Kit and
Isaac Sim adapters are loaded lazily by their process-specific entry points.
"""

from .core.models import ProjectDefinition

__all__ = ["ProjectDefinition"]
__version__ = "0.2.1"
