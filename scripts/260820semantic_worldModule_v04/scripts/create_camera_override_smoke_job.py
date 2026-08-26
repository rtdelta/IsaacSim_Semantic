"""Create a one-frame JobSpec that proves Stage/override/effective parameters."""

import argparse
import json
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler
from semantic_world_v04.core.models import (
    CaptureSchedule,
    ModalityDefinition,
    OutputPolicy,
    ProjectDefinition,
    RenderProfile,
    StageReference,
    VariantDefinition,
)
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.plugins.sensors import PinholeCameraPlugin
from semantic_world_v04.project import ProjectRepository
from semantic_world_v04.stage.omni_adapter import build_stage_index


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--renderer", default="RayTracedLighting")
    parser.add_argument("--focal-length", type=float)
    parser.add_argument("--override-transform", action="store_true")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    from isaacsim import SimulationApp  # type: ignore

    app = SimulationApp({"headless": True, "multi_gpu": False})
    try:
        from pxr import Usd  # type: ignore

        stage = Usd.Stage.Open(args.stage)
        if stage is None:
            raise RuntimeError(f"failed to open Stage: {args.stage}")
        stage_index = build_stage_index(stage)
        camera_prim = stage_index.require(args.camera)
        plugin = PinholeCameraPlugin()
        sensor = plugin.definition_from_prim("camera", camera_prim)
        original_focal = float(sensor.parameters["focalLength"])
        override_focal = (
            float(args.focal_length)
            if args.focal_length is not None
            else original_focal + 7.0
        )
        sensor.parameters["focalLength"] = override_focal
        sensor.parameter_sources["focalLength"] = "override"
        sensor.parameters["resolution"] = [160, 90]
        sensor.parameter_sources["resolution"] = "override"
        if args.override_transform:
            sensor.parameters["transform"] = sensor.stage_parameters["transform"]
            sensor.parameter_sources["transform"] = "override"

        project = ProjectDefinition(
            project_id=args.job_id,
            name="v04 camera override smoke",
            stage=StageReference(args.stage),
            sensors=[sensor],
            variants=[
                VariantDefinition(
                    variant_id="full_scene",
                    strategy="full_scene",
                    modalities_by_sensor={"camera": ["rgb", "semantic_id"]},
                )
            ],
            modalities=[
                ModalityDefinition("rgb", "rgb"),
                ModalityDefinition("semantic_id", "semantic_id"),
                ModalityDefinition("semantic_color", "semantic_color"),
            ],
            render=RenderProfile(
                renderer=args.renderer,
                resolution_width=160,
                resolution_height=90,
                warmup_frames=2,
                rt_subframes=1,
                spp_per_frame=1,
                total_spp=1,
                max_bounces=2,
            ),
            capture=CaptureSchedule(frame_count=1, segment_frames=1),
            output=OutputPolicy(root_dir=args.output_root),
        )
        project_dir = Path(args.project_dir)
        ProjectRepository().save(project_dir, project)
        job = JobCompiler().compile(
            project,
            source_project_path=str(project_dir),
            stage_index=stage_index,
            job_id=args.job_id,
        )
        spec_path = project_dir / "jobs" / args.job_id / "job_spec.json"
        atomic_write_json(spec_path, job.to_dict())
        print(
            json.dumps(
                {
                    "job_spec": str(spec_path),
                    "original_focal_length": original_focal,
                    "override_focal_length": override_focal,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
