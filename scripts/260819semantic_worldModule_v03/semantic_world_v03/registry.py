"""Sensor plugin registry; the core never branches on concrete sensor types."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .errors import ConfigurationError

if TYPE_CHECKING:
    from .config import SensorConfig
    from .sensors.base import BaseSensorDriver


SensorFactory = Callable[["SensorConfig"], "BaseSensorDriver"]


class SensorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, SensorFactory] = {}

    @property
    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def register(
        self,
        sensor_type: str,
        factory: SensorFactory,
        *,
        replace: bool = False,
    ) -> None:
        sensor_type = str(sensor_type).strip()
        if not sensor_type:
            raise ValueError("sensor_type must not be empty")
        if not callable(factory):
            raise TypeError("Sensor factory must be callable")
        if sensor_type in self._factories and not replace:
            raise ValueError(f"Sensor type is already registered: {sensor_type}")
        self._factories[sensor_type] = factory

    def create(self, spec: "SensorConfig") -> "BaseSensorDriver":
        try:
            factory = self._factories[spec.sensor_type]
        except KeyError as exc:
            available = ", ".join(self.types) or "<none>"
            raise ConfigurationError(
                f"Sensor {spec.sensor_id} uses unregistered type {spec.sensor_type!r}; "
                f"available types: {available}"
            ) from exc
        driver = factory(spec)
        if driver.sensor_id != spec.sensor_id:
            raise RuntimeError(
                f"Factory for {spec.sensor_type} returned driver {driver.sensor_id!r}, "
                f"expected {spec.sensor_id!r}"
            )
        return driver


def build_default_registry(plugins: dict[str, str] | None = None) -> SensorRegistry:
    from .sensors.camera import FisheyeCameraDriver, PinholeCameraDriver
    from .sensors.lidar import RtxLidarDriver

    registry = SensorRegistry()
    registry.register("camera.pinhole", PinholeCameraDriver)
    registry.register("camera.fisheye_opencv", FisheyeCameraDriver)
    registry.register("lidar.rtx.rotary", RtxLidarDriver)
    registry.register("lidar.rtx.solid_state", RtxLidarDriver)
    for sensor_type, class_path in (plugins or {}).items():
        module_name, class_name = class_path.split(":", 1)
        factory = getattr(importlib.import_module(module_name), class_name)
        registry.register(sensor_type, factory, replace=True)
    return registry
