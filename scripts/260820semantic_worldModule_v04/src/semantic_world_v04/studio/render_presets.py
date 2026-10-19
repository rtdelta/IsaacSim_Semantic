"""Render presets exposed by the Studio without coupling them to omni.ui."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from semantic_world_v04.core.models import RenderProfile


@dataclass(frozen=True)
class RenderPreset:
    preset_id: str
    display_name: str
    description: str
    profile: RenderProfile

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "description": self.description,
            "profile": asdict(self.profile),
        }


PATH_TRACING_PRODUCTION = RenderPreset(
    preset_id="pathtracing_production",
    display_name="Path Tracing 正式质量",
    description="1280×720, 64 total SPP, 4 bounces, denoiser enabled",
    profile=RenderProfile(
        renderer="PathTracing",
        resolution_width=1280,
        resolution_height=720,
        warmup_frames=16,
        rt_subframes=1,
        spp_per_frame=8,
        total_spp=64,
        max_bounces=4,
        denoiser=True,
    ),
)

PATH_TRACING_PREVIEW = RenderPreset(
    preset_id="pathtracing_preview",
    display_name="Path Tracing 快速验证",
    description="640×360, 1 SPP smoke profile",
    profile=RenderProfile(
        renderer="PathTracing",
        resolution_width=640,
        resolution_height=360,
        warmup_frames=4,
        rt_subframes=1,
        spp_per_frame=1,
        total_spp=1,
        max_bounces=2,
        denoiser=True,
    ),
)

REALTIME_PREVIEW = RenderPreset(
    preset_id="realtime_preview",
    display_name="Realtime 快速验证",
    description="640×360 RayTracedLighting smoke profile",
    profile=RenderProfile(
        renderer="RayTracedLighting",
        resolution_width=640,
        resolution_height=360,
        warmup_frames=4,
        rt_subframes=1,
        spp_per_frame=1,
        total_spp=1,
        max_bounces=2,
        denoiser=True,
    ),
)

RENDER_PRESETS = (
    PATH_TRACING_PRODUCTION,
    PATH_TRACING_PREVIEW,
    REALTIME_PREVIEW,
)

DEFAULT_RENDER_PRESET_ID = PATH_TRACING_PRODUCTION.preset_id


def render_preset(preset_id: str) -> RenderPreset:
    for preset in RENDER_PRESETS:
        if preset.preset_id == preset_id:
            return preset
    raise KeyError(f"unknown render preset: {preset_id}")


def render_preset_catalog() -> List[Dict[str, Any]]:
    return [preset.to_dict() for preset in RENDER_PRESETS]


def render_profile_for_preset(preset_id: str) -> RenderProfile:
    return RenderProfile.from_dict(asdict(render_preset(preset_id).profile))


def matching_render_preset(profile: RenderProfile) -> Optional[str]:
    value = asdict(profile)
    for preset in RENDER_PRESETS:
        if value == asdict(preset.profile):
            return preset.preset_id
    return None
