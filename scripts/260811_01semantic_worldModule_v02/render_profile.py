"""Versioned, reproducible render settings for Isaac Sim capture."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping


LEGACY_RENDER_PROFILE_SCHEMA_VERSION = 1
RENDER_PROFILE_SCHEMA_VERSION = 2
SUPPORTED_RENDERERS = ("RealTimePathTracing", "PathTracing")
LEGACY_RENDERERS = ("RaytracedLighting",)
ALLOWED_LAUNCH_SETTINGS = {
    "anti_aliasing",
    "denoiser",
    "samples_per_pixel_per_frame",
    "max_bounces",
    "max_specular_transmission_bounces",
    "max_volume_bounces",
    "multi_gpu",
    "max_gpu_count",
}
DEFAULT_WARMUP_RENDER_FRAMES = 16


def sha256_file(path: str | Path) -> str:
    resolved = Path(path).resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SettingMismatch:
    key: str
    requested: Any
    effective: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "requested": self.requested,
            "effective": self.effective,
        }


class RenderProfileApplicationError(RuntimeError):
    """Required settings failed read-back; retain the full snapshot for the manifest."""

    def __init__(self, message: str, snapshot: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.snapshot = dict(snapshot)


def _as_object(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Render profile {key} must be a JSON object")
    return dict(value)


def _validate_positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0 or parsed != value:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


@dataclass(frozen=True)
class RenderProfile:
    schema_version: int
    source_path: Path
    source_sha256: str
    name: str
    renderer: str
    launch_settings: Mapping[str, Any]
    capture_settings: Mapping[str, Any]
    settings: Mapping[str, Any]
    required_settings: tuple[str, ...]
    metadata: Mapping[str, Any]

    @property
    def rt_subframes(self) -> int:
        return int(self.capture_settings["rt_subframes"])

    @property
    def warmup_render_frames(self) -> int:
        return int(self.capture_settings["warmup_render_frames"])

    @property
    def is_path_tracing(self) -> bool:
        return self.renderer == "PathTracing"

    @property
    def is_realtime_path_tracing(self) -> bool:
        return self.renderer == "RealTimePathTracing"

    @classmethod
    def load(cls, path: str | Path) -> "RenderProfile":
        resolved = Path(path).resolve()
        with resolved.open("r", encoding="utf-8") as stream:
            raw = json.load(stream)
        schema_version = int(raw.get("schema_version", 0))
        if schema_version not in {
            LEGACY_RENDER_PROFILE_SCHEMA_VERSION,
            RENDER_PROFILE_SCHEMA_VERSION,
        }:
            raise ValueError(f"Unsupported render profile schema version: {schema_version}")

        name = str(raw.get("name", "")).strip()
        renderer = str(raw.get("renderer", "")).strip()
        settings = _as_object(raw, "settings")
        metadata = _as_object(raw, "metadata")
        required = raw.get("required_settings", list(settings))
        if not name or not renderer:
            raise ValueError("Render profile name and renderer must not be empty")
        if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
            raise ValueError("required_settings must be a list of setting keys")
        missing = sorted(set(required) - set(settings))
        if missing:
            raise ValueError(f"Required render settings are not defined: {missing}")

        if schema_version == LEGACY_RENDER_PROFILE_SCHEMA_VERSION:
            if renderer not in {*SUPPORTED_RENDERERS, *LEGACY_RENDERERS}:
                raise ValueError(f"Unsupported legacy renderer: {renderer}")
            launch_settings: dict[str, Any] = {}
            capture_settings = {
                "rt_subframes": _validate_positive_integer(
                    raw.get("rt_subframes", 0), "rt_subframes"
                ),
                "warmup_render_frames": DEFAULT_WARMUP_RENDER_FRAMES,
            }
        else:
            if renderer not in SUPPORTED_RENDERERS:
                raise ValueError(
                    f"Schema-v2 renderer must be one of {SUPPORTED_RENDERERS}, got {renderer!r}"
                )
            launch_settings = _as_object(raw, "launch_settings")
            unknown_launch_settings = sorted(set(launch_settings) - ALLOWED_LAUNCH_SETTINGS)
            if unknown_launch_settings:
                raise ValueError(
                    f"Unsupported SimulationApp launch settings: {unknown_launch_settings}"
                )
            capture_settings = _as_object(raw, "capture_settings")
            capture_settings = {
                **capture_settings,
                "rt_subframes": _validate_positive_integer(
                    capture_settings.get("rt_subframes", 0),
                    "capture_settings.rt_subframes",
                ),
                "warmup_render_frames": _validate_positive_integer(
                    capture_settings.get("warmup_render_frames", 0),
                    "capture_settings.warmup_render_frames",
                ),
            }
            cls._validate_mode_settings(
                renderer=renderer,
                launch_settings=launch_settings,
                settings=settings,
                required_settings=tuple(required),
            )

        return cls(
            schema_version=schema_version,
            source_path=resolved,
            source_sha256=sha256_file(resolved),
            name=name,
            renderer=renderer,
            launch_settings=launch_settings,
            capture_settings=capture_settings,
            settings=settings,
            required_settings=tuple(required),
            metadata=metadata,
        )

    @staticmethod
    def _validate_mode_settings(
        renderer: str,
        launch_settings: Mapping[str, Any],
        settings: Mapping[str, Any],
        required_settings: tuple[str, ...],
    ) -> None:
        render_mode_key = "/rtx/rendermode"
        if settings.get(render_mode_key) != renderer:
            raise ValueError(
                f"{render_mode_key} must equal profile renderer {renderer!r}"
            )
        if render_mode_key not in required_settings:
            raise ValueError(f"{render_mode_key} must be a required setting")

        dlss_keys = {"rtx/post/dlss/execMode", "/rtx/post/dlss/execMode"}
        path_sampling_keys = {"/rtx/pathtracing/spp", "/rtx/pathtracing/totalSpp"}
        if renderer == "RealTimePathTracing":
            if path_sampling_keys & set(settings):
                raise ValueError("RealTimePathTracing profile must not define PathTracing SPP")
            configured_dlss = dlss_keys & set(settings)
            if len(configured_dlss) != 1:
                raise ValueError("RealTimePathTracing profile must define exactly one DLSS execMode")
            dlss_key = next(iter(configured_dlss))
            if settings[dlss_key] not in {0, 1, 2, 3}:
                raise ValueError("DLSS execMode must be 0, 1, 2, or 3")
            if dlss_key not in required_settings:
                raise ValueError("DLSS execMode must be a required setting")
            if launch_settings.get("anti_aliasing") != 3:
                raise ValueError("RealTimePathTracing profile must launch with DLSS anti_aliasing=3")
            if "samples_per_pixel_per_frame" in launch_settings:
                raise ValueError(
                    "samples_per_pixel_per_frame is only valid in the PathTracing profile"
                )
        elif renderer == "PathTracing":
            if dlss_keys & set(settings):
                raise ValueError("PathTracing profile must not define a DLSS execMode")
            missing_sampling = sorted(path_sampling_keys - set(settings))
            if missing_sampling:
                raise ValueError(f"PathTracing settings are missing: {missing_sampling}")
            missing_required_sampling = sorted(path_sampling_keys - set(required_settings))
            if missing_required_sampling:
                raise ValueError(
                    f"PathTracing sampling settings must be required: {missing_required_sampling}"
                )
            spp = _validate_positive_integer(settings["/rtx/pathtracing/spp"], "PathTracing spp")
            if spp > 32:
                raise ValueError("PathTracing spp must be between 1 and 32")
            total_spp = int(settings["/rtx/pathtracing/totalSpp"])
            if total_spp < 0 or (total_spp != 0 and total_spp < spp):
                raise ValueError("PathTracing totalSpp must be 0 or at least spp")
            if launch_settings.get("samples_per_pixel_per_frame") != spp:
                raise ValueError(
                    "PathTracing launch samples_per_pixel_per_frame must equal /rtx/pathtracing/spp"
                )
            if not isinstance(launch_settings.get("denoiser"), bool):
                raise ValueError("PathTracing profile must explicitly set launch denoiser")
            if launch_settings.get("anti_aliasing") != 0:
                raise ValueError("PathTracing profile must disable DLSS anti_aliasing with value 0")
            reset_key = "/rtx/resetPtAccumOnAnimTimeChange"
            if settings.get(reset_key) is not True or reset_key not in required_settings:
                raise ValueError(
                    "PathTracing profile must require resetPtAccumOnAnimTimeChange=true"
                )

    def with_capture_overrides(
        self,
        rt_subframes: int | None = None,
        warmup_render_frames: int | None = None,
    ) -> "RenderProfile":
        capture_settings = dict(self.capture_settings)
        if rt_subframes is not None:
            capture_settings["rt_subframes"] = _validate_positive_integer(
                rt_subframes, "rt_subframes override"
            )
        if warmup_render_frames is not None:
            if isinstance(warmup_render_frames, bool) or int(warmup_render_frames) < 0:
                raise ValueError("warmup-render-frames override must be non-negative")
            capture_settings["warmup_render_frames"] = int(warmup_render_frames)
        return replace(self, capture_settings=capture_settings)

    def with_rt_subframes(self, value: int | None) -> "RenderProfile":
        """Backward-compatible convenience wrapper used by existing callers and tests."""
        return self.with_capture_overrides(rt_subframes=value)

    def launch_config(self, headless: bool) -> dict[str, Any]:
        return {
            "headless": bool(headless),
            "renderer": self.renderer,
            "sync_loads": True,
            **dict(self.launch_settings),
        }

    def sampling_summary(self) -> dict[str, Any]:
        if self.is_path_tracing:
            spp = int(self.settings["/rtx/pathtracing/spp"])
            total_spp = int(self.settings["/rtx/pathtracing/totalSpp"])
            nominal = spp * self.rt_subframes
            return {
                "model": "path_tracing_spp",
                "spp_per_render_frame": spp,
                "rt_subframes": self.rt_subframes,
                "nominal_spp_per_output": nominal,
                "total_spp_cap": total_spp,
                "planned_spp_per_output": min(nominal, total_spp)
                if total_spp > 0
                else nominal,
                "denoiser": bool(self.launch_settings["denoiser"]),
                "accumulation_reset_on_time_change": bool(
                    self.settings["/rtx/resetPtAccumOnAnimTimeChange"]
                ),
            }
        dlss_key = next(
            (
                key
                for key in ("/rtx/post/dlss/execMode", "rtx/post/dlss/execMode")
                if key in self.settings
            ),
            None,
        )
        return {
            "model": "realtime_temporal_subframes",
            "rt_subframes": self.rt_subframes,
            "dlss_exec_mode": self.settings.get(dlss_key) if dlss_key else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "path": str(self.source_path),
            "sha256": self.source_sha256,
            "name": self.name,
            "renderer": self.renderer,
            "launch_settings": dict(self.launch_settings),
            "capture_settings": dict(self.capture_settings),
            "settings": dict(self.settings),
            "required_settings": list(self.required_settings),
            "metadata": dict(self.metadata),
        }


def _equal_setting(requested: Any, effective: Any) -> bool:
    if isinstance(requested, bool) or isinstance(effective, bool):
        return requested is effective
    if isinstance(requested, (int, float)) and isinstance(effective, (int, float)):
        return math.isclose(float(requested), float(effective), rel_tol=0.0, abs_tol=1e-9)
    return requested == effective


class RenderProfileManager:
    """Apply raw Carb settings and retain an auditable read-back snapshot."""

    def __init__(self, settings_interface: Any) -> None:
        self._settings = settings_interface

    def apply_and_snapshot(self, profile: RenderProfile) -> dict[str, Any]:
        initial = {key: self._settings.get(key) for key in profile.settings}
        for key, value in profile.settings.items():
            self._settings.set(key, value)
        effective = {key: self._settings.get(key) for key in profile.settings}
        mismatches = [
            SettingMismatch(key=key, requested=profile.settings[key], effective=effective[key])
            for key in profile.required_settings
            if not _equal_setting(profile.settings[key], effective[key])
        ]
        render_mode_key = "/rtx/rendermode"
        snapshot = {
            "profile": profile.to_dict(),
            "renderer": {
                "requested": profile.renderer,
                "effective": effective.get(render_mode_key),
            },
            "launch": dict(profile.launch_settings),
            "capture": dict(profile.capture_settings),
            "sampling": profile.sampling_summary(),
            "initial": initial,
            "requested": dict(profile.settings),
            "effective": effective,
            "mismatches": [item.to_dict() for item in mismatches],
        }
        if mismatches:
            details = ", ".join(
                f"{item.key}: requested={item.requested!r}, effective={item.effective!r}"
                for item in mismatches
            )
            raise RenderProfileApplicationError(
                f"Required render settings did not take effect: {details}",
                snapshot=snapshot,
            )
        return snapshot
