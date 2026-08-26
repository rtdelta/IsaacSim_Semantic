"""Render profile loading and one-trigger-per-render-group acquisition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import RenderGroupConfig
from .models import CaptureRequest, SensorPacket


@dataclass(frozen=True)
class RenderProfile:
    path: Path
    sha256: str
    renderer: str
    launch_settings: dict[str, Any]
    settings: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> "RenderProfile":
        source = Path(path).resolve()
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Render profile must be an object: {source}")
        renderer = raw.get("renderer")
        if renderer not in {"RealTimePathTracing", "PathTracing"}:
            raise ValueError(f"Unsupported renderer in {source}: {renderer}")
        launch = raw.get("launch_settings", {})
        settings = raw.get("settings", {})
        if not isinstance(launch, dict) or not isinstance(settings, dict):
            raise ValueError(f"Render profile launch_settings/settings must be objects: {source}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        return cls(source, digest, renderer, dict(launch), dict(settings))

    def launch_config(self, *, headless: bool) -> dict[str, Any]:
        return {
            "headless": headless,
            "renderer": self.renderer,
            "sync_loads": True,
            **self.launch_settings,
        }


def resolve_profiles(groups: Iterable[RenderGroupConfig]) -> dict[str, RenderProfile]:
    profiles = {
        group.group_id: RenderProfile.load(group.profile)
        for group in groups
        if group.profile is not None
    }
    renderer_values = {profile.renderer for profile in profiles.values()}
    if len(renderer_values) > 1:
        raise ValueError(
            "One worker cannot use render groups with different global RTX renderers"
        )
    setting_values: dict[str, Any] = {}
    for profile in profiles.values():
        for key, value in profile.settings.items():
            if key in setting_values and setting_values[key] != value:
                raise ValueError(f"Render profiles disagree on global setting {key}")
            setting_values[key] = value
    return profiles


class IsaacRenderBackend:
    def __init__(self, simulation_app: Any) -> None:
        self.simulation_app = simulation_app

    def render(self, *, rt_subframes: int) -> None:
        import omni.replicator.core as rep

        rep.orchestrator.step(
            rt_subframes=rt_subframes,
            delta_time=0.0,
            pause_timeline=False,
            wait_for_render=True,
        )
        rep.orchestrator.wait_until_complete()

    def update(self, count: int = 1) -> None:
        for _ in range(count):
            self.simulation_app.update()


class RenderGroupManager:
    def __init__(self, backend: IsaacRenderBackend, group_specs: dict[str, RenderGroupConfig]) -> None:
        self.backend = backend
        self.group_specs = group_specs

    def acquire(
        self,
        drivers_and_requests: Iterable[tuple[Any, CaptureRequest]],
    ) -> tuple[SensorPacket, ...]:
        packets, errors = self.acquire_with_errors(drivers_and_requests)
        if errors:
            raise next(iter(errors.values()))
        return packets

    def acquire_with_errors(
        self,
        drivers_and_requests: Iterable[tuple[Any, CaptureRequest]],
    ) -> tuple[tuple[SensorPacket, ...], dict[str, Exception]]:
        grouped: dict[str, list[tuple[Any, CaptureRequest]]] = {}
        for driver, request in drivers_and_requests:
            grouped.setdefault(request.render_group, []).append((driver, request))
        packets: list[SensorPacket] = []
        errors: dict[str, Exception] = {}
        for group_id, members in grouped.items():
            group = self.group_specs[group_id]
            execution = getattr(group, "execution", "batched")
            if execution == "batched" and any(
                driver.capabilities.requires_render_trigger for driver, _ in members
            ):
                self.backend.render(rt_subframes=group.rt_subframes)
            for driver, request in members:
                try:
                    if execution == "serial" and driver.capabilities.requires_render_trigger:
                        self.backend.render(rt_subframes=group.rt_subframes)
                    packet = driver.read(request)
                    driver.mark_sample_captured()
                    packets.append(packet)
                except Exception as exc:
                    errors[request.sensor_id] = exc
        return tuple(packets), errors
