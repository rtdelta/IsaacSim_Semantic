"""Semantic camera scheduling only; app, world, and motion are owned elsewhere."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import carb.settings
import omni.replicator.core as rep
from omni.replicator.core.backends import DiskBackend
from pxr import Usd, UsdGeom

from semantic_dataset_writer import SemanticDatasetWriter


class SemanticCameraScheduler:
    """Own one Camera RenderProduct and its semantic dataset Writer."""

    def __init__(
        self,
        simulation_app: Any,
        stage: Any,
        camera_path: str | None,
        cab_root: str,
        output_path: Path,
        mapping_path: Path,
        width: int,
        height: int,
        rt_subframes: int,
        save_runtime_ids: bool,
        strict_mapping: bool,
    ) -> None:
        self._app = simulation_app
        self._stage = stage
        self._requested_camera_path = camera_path
        self._cab_root = cab_root
        self._output_path = Path(output_path)
        self._mapping_path = Path(mapping_path)
        self._width = int(width)
        self._height = int(height)
        self._rt_subframes = int(rt_subframes)
        self._save_runtime_ids = bool(save_runtime_ids)
        self._strict_mapping = bool(strict_mapping)
        self._render_product = None
        self._writer = None
        self._backend = None
        self.camera_path = ""

    def _resolve_camera_path(self) -> str:
        if self._requested_camera_path:
            prim = self._stage.GetPrimAtPath(self._requested_camera_path)
            if not prim.IsValid() or not prim.IsA(UsdGeom.Camera):
                raise RuntimeError(f"Camera prim is missing or invalid: {self._requested_camera_path}")
            if not str(prim.GetPath()).startswith(self._cab_root.rstrip("/") + "/"):
                raise RuntimeError(
                    f"Camera {prim.GetPath()} is not a descendant of cab root {self._cab_root}"
                )
            return str(prim.GetPath())

        cab_prim = self._stage.GetPrimAtPath(self._cab_root)
        if not cab_prim.IsValid():
            raise RuntimeError(f"Cab root is missing: {self._cab_root}")
        cameras = [
            str(prim.GetPath())
            for prim in Usd.PrimRange(cab_prim)
            if prim.IsA(UsdGeom.Camera)
        ]
        if len(cameras) != 1:
            raise RuntimeError(
                f"Expected exactly one Camera below {self._cab_root}, found {len(cameras)}: {cameras}"
            )
        return cameras[0]

    def initialize(self) -> None:
        self.camera_path = self._resolve_camera_path()
        semantic_prim_count = sum(
            any(str(schema).startswith("SemanticsLabelsAPI") for schema in prim.GetAppliedSchemas())
            for prim in self._stage.Traverse()
        )
        if semantic_prim_count == 0:
            raise RuntimeError("No SemanticsLabelsAPI labels were found in the stage")

        carb.settings.get_settings().set("rtx/post/dlss/execMode", 2)
        rep.orchestrator.set_capture_on_play(False)
        self._render_product = rep.create.render_product(
            self.camera_path,
            resolution=(self._width, self._height),
            name="SemanticCapture",
        )
        self._backend = DiskBackend(output_dir=str(self._output_path), overwrite=True)
        self._writer = SemanticDatasetWriter(
            backend=self._backend,
            semantic_schema=str(self._mapping_path),
            rgb=True,
            save_runtime_ids=self._save_runtime_ids,
            strict_mapping=self._strict_mapping,
        )
        self._writer.attach(self._render_product)
        print(
            f"[semantic-camera] Camera={self.camera_path}, resolution={self._width}x{self._height}, "
            f"semantic prims={semantic_prim_count}"
        )

    def warmup(self, update_count: int) -> None:
        if self._render_product is None:
            raise RuntimeError("SemanticCameraScheduler.initialize() must be called before warmup()")
        self._render_product.hydra_texture.set_updates_enabled(True)
        for _ in range(update_count):
            self._app.update()
        self._render_product.hydra_texture.set_updates_enabled(False)

    def capture(self, frame_id: int, simulation_time: float) -> None:
        if self._render_product is None:
            raise RuntimeError("SemanticCameraScheduler is not initialized")
        _ = frame_id, simulation_time
        self._render_product.hydra_texture.set_updates_enabled(True)
        rep.orchestrator.step(
            rt_subframes=self._rt_subframes,
            delta_time=0.0,
            pause_timeline=False,
        )
        self._render_product.hydra_texture.set_updates_enabled(False)

    def wait_until_complete(self) -> None:
        rep.orchestrator.wait_until_complete()

    def get_state(self) -> dict[str, Any]:
        prim = self._stage.GetPrimAtPath(self.camera_path)
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        matrix = cache.GetLocalToWorldTransform(prim)
        return {
            "path": self.camera_path,
            "world_transform": [
                float(matrix[row][column]) for row in range(4) for column in range(4)
            ],
        }

    def close(self) -> None:
        if self._writer is not None:
            self._writer.detach()
            self._writer = None
        if self._render_product is not None:
            self._render_product.destroy()
            self._render_product = None
