"""Semantic World Module v03.

The package deliberately has no import-time dependency on Isaac Sim.  Config
validation, supervision, ledger inspection, and unit tests therefore run in a
normal Python interpreter.  Isaac modules are imported only by the worker and
the concrete sensor drivers after ``SimulationApp`` has started.
"""

from .config import RunConfig, load_run_config
from .models import CaptureRequest, SensorPacket, WorldSnapshot
from .registry import SensorRegistry, build_default_registry

__all__ = [
    "CaptureRequest",
    "RunConfig",
    "SensorPacket",
    "SensorRegistry",
    "WorldSnapshot",
    "build_default_registry",
    "load_run_config",
]

__version__ = "0.1.0"

