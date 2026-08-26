"""Create one configurable validation project and immutable JobSpec."""

import argparse
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler
from semantic_world_v04.core.models import (
    CaptureSchedule,
    ExecutionPolicy,
    ModalityDefinition,
    MotionSpec,
    OutputPolicy,
    ProjectDefinition,
    RenderProfile,
    SensorDefinition,
    StageReference,
    VariantDefinition,
)
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.project import ProjectRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--renderer", choices=["RayTracedLighting", "PathTracing"], required=True
    )
    parser.add_argument("--frame-count", type=int, default=5)
    parser.add_argument("--segment-frames", type=int, default=2)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--warmup-frames", type=int, default=4)
    parser.add_argument("--spp", type=int, default=1)
    parser.add_argument(
        "--stage",
        default=(
            "/root/gpufree-data/IsaacSim_Asset/combine_stage/"
            "combine_scene_05.usda"
        ),
    )
    parser.add_argument(
        "--camera", default="/Excavator_Fangshan_03/boom_prim/Camera"
    )
    parser.add_argument("--trajectory")
    parser.add_argument(
        "--articulation-prim", default="/Excavator_Fangshan_03/track_prim"
    )
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    motion = MotionSpec()
    if args.trajectory:
        motion = MotionSpec(
            plugin="csv_articulation",
            source_path=args.trajectory,
            supports_absolute_seek=True,
            options={
                "articulation_prim_path": args.articulation_prim,
                "time_column": "time",
                "joint_columns": {
                    "track_operator_cab_joint": "cab",
                    "platform_boom_joint": "boom",
                    "boom_small_arm_joint": "small_arm",
                    "small_arm_bucket_joint": "bucket",
                },
                "interpolation": "linear",
                "angle_units": "degrees",
                "root_pose": {
                    "position": [
                        "root_world_x_m",
                        "root_world_y_m",
                        "root_world_z_m",
                    ],
                    "orientation_wxyz": [
                        "root_quat_w",
                        "root_quat_x",
                        "root_quat_y",
                        "root_quat_z",
                    ],
                },
            },
        )
    project = ProjectDefinition(
        project_id=args.job_id,
        name=f"v04.2 validation {args.renderer}",
        stage=StageReference(args.stage),
        sensors=[
            SensorDefinition(
                sensor_id="boom_camera",
                plugin="pinhole_camera",
                prim_path=args.camera,
            )
        ],
        variants=[
            VariantDefinition(
                variant_id="full_scene",
                strategy="full_scene",
                modalities_by_sensor={
                    "boom_camera": ["rgb", "semantic_id", "semantic_color"]
                },
            ),
            VariantDefinition(
                variant_id="excavator_only",
                strategy="include_paths",
                include_paths=["/Environment", "/Excavator_Fangshan_03"],
                modalities_by_sensor={
                    "boom_camera": ["semantic_id", "semantic_color"]
                },
            ),
        ],
        modalities=[
            ModalityDefinition("rgb", "rgb"),
            ModalityDefinition("semantic_id", "semantic_id"),
            ModalityDefinition("semantic_color", "semantic_color"),
        ],
        render=RenderProfile(
            renderer=args.renderer,
            resolution_width=args.width,
            resolution_height=args.height,
            warmup_frames=args.warmup_frames,
            rt_subframes=1,
            spp_per_frame=args.spp,
            total_spp=args.spp,
            max_bounces=2,
            denoiser=True,
        ),
        capture=CaptureSchedule(
            physics_hz=60,
            capture_fps=10,
            start_frame=0,
            frame_count=args.frame_count,
            capture_initial_frame=True,
            segment_frames=args.segment_frames,
        ),
        output=OutputPolicy(root_dir=args.output_root),
        motion=motion,
        execution=ExecutionPolicy(
            heartbeat_timeout_seconds=120,
            no_progress_timeout_seconds=300,
            segment_start_timeout_seconds=180,
            graceful_stop_timeout_seconds=20,
            telemetry_interval_seconds=2,
        ),
    )
    workspace = Path(args.workspace)
    project_dir = workspace / f"{args.job_id}.swproject"
    ProjectRepository().save(project_dir, project)
    job = JobCompiler().compile(
        project,
        source_project_path=project_dir.as_posix(),
        job_id=args.job_id,
    )
    job_path = project_dir / "jobs" / job.job_id / "job_spec.json"
    atomic_write_json(job_path, job.to_dict())
    print(job_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
