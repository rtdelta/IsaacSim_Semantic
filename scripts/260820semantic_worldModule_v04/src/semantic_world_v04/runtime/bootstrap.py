"""SimulationApp lifecycle, Stage loading, and verified render settings."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from semantic_world_v04.core.models import JobSpec, RenderProfile
from semantic_world_v04.project.paths import ProjectPathResolver


def loaded_libpython() -> str:
    if os.name != "nt":
        try:
            for line in Path("/proc/self/maps").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if "libpython" in line:
                    return line.rsplit(None, 1)[-1]
        except OSError:
            pass
    return "unknown"


class SimulationRuntime:
    def __init__(self, job_spec: JobSpec) -> None:
        self.job_spec = job_spec
        self.app = None
        self.stage = None
        self.render_snapshot: Dict[str, Any] = {}

    def start(self) -> None:
        render = self.job_spec.project.render
        launch = {
            "headless": True,
            "renderer": render.renderer,
            "width": render.resolution_width,
            "height": render.resolution_height,
            "anti_aliasing": 0,
            "denoiser": render.denoiser,
            "samples_per_pixel_per_frame": render.spp_per_frame,
            "max_bounces": render.max_bounces,
            "multi_gpu": False,
            "max_gpu_count": 1,
            "sync_loads": True,
        }
        from isaacsim import SimulationApp  # type: ignore

        self.app = SimulationApp(launch)

    def open_stage(self, max_updates: int = 1800) -> Any:
        if self.app is None:
            raise RuntimeError("SimulationApp has not started")
        import omni.usd  # type: ignore

        stage_path = self.job_spec.project.stage.usd_path
        if self.job_spec.source_project_path:
            stage_path = str(
                ProjectPathResolver.resolve(
                    stage_path, Path(self.job_spec.source_project_path)
                )
            )
        context = omni.usd.get_context()
        if not context.open_stage(stage_path):
            raise RuntimeError(f"could not start opening USD Stage: {stage_path}")
        last_status = None
        for _ in range(max_updates):
            self.app.update()
            stage = context.get_stage()
            last_status = context.get_stage_loading_status()
            pending = int(last_status[2]) if len(last_status) > 2 else 0
            if (
                stage is not None
                and pending == 0
                and bool(stage.GetPseudoRoot().GetChildren())
            ):
                self.stage = stage
                return stage
        raise TimeoutError(
            f"USD Stage did not finish loading: {stage_path}; status={last_status}"
        )

    def apply_render_settings(self) -> Dict[str, Any]:
        if self.app is None or self.stage is None:
            raise RuntimeError("Stage must be open before render settings are applied")
        import carb.settings  # type: ignore

        render = self.job_spec.project.render
        self.app.reset_render_settings()
        requested = self._requested_render_settings(render)
        settings = carb.settings.get_settings()
        for key, value in requested.items():
            settings.set(key, value)
        effective = {key: settings.get(key) for key in requested}
        mismatch = {
            key: {"requested": requested[key], "effective": effective[key]}
            for key in requested
            if requested[key] != effective[key]
        }
        if mismatch:
            raise RuntimeError(
                "render settings failed read-back: "
                + json.dumps(mismatch, ensure_ascii=False, sort_keys=True)
            )
        self.render_snapshot = {
            "renderer": render.renderer,
            "requested": requested,
            "effective": effective,
            "sys_executable": sys.executable,
            "sys_version": sys.version,
            "libpython": loaded_libpython(),
        }
        return self.render_snapshot

    def warmup(self, count: Optional[int] = None) -> None:
        if self.app is None:
            raise RuntimeError("SimulationApp has not started")
        frames = self.job_spec.project.render.warmup_frames if count is None else count
        for _ in range(frames):
            self.app.update()

    def close(self) -> None:
        if self.app is not None:
            self.app.close()
            self.app = None
            self.stage = None

    @staticmethod
    def reset_render_history() -> None:
        try:
            import carb.settings  # type: ignore

            settings = carb.settings.get_settings()
            path = "/rtx/externalFrameCounter"
            settings.set_int(path, int(settings.get(path) or 0) + 1)
        except Exception:
            return

    @staticmethod
    def _requested_render_settings(render: RenderProfile) -> Dict[str, Any]:
        requested: Dict[str, Any] = dict(render.settings)
        if render.renderer == "PathTracing":
            defaults = {
                "/rtx/rendermode": "PathTracing",
                "/rtx/pathtracing/spp": render.spp_per_frame,
                "/rtx/pathtracing/totalSpp": render.total_spp,
                "/rtx/pathtracing/adaptiveSampling/enabled": False,
                "/rtx/pathtracing/maxBounces": render.max_bounces,
                "/rtx/resetPtAccumOnAnimTimeChange": True,
                "/rtx/pathtracing/fractionalCutoutOpacity": True,
            }
            for key, value in defaults.items():
                requested.setdefault(key, value)
        return requested
