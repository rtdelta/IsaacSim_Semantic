"""Create a real heterogeneous-sensor JobSpec for cloud validation."""

import argparse
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler
from semantic_world_v04.core.models import (
    CaptureSchedule,
    ExecutionPolicy,
    ModalityDefinition,
    OutputPolicy,
    ProjectDefinition,
    RenderProfile,
    SensorDefinition,
    StageReference,
    VariantDefinition,
)
from semantic_world_v04.core.sensor_models import RigDefinition
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.project import ProjectRepository


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--renderer",
        choices=["RayTracedLighting", "PathTracing"],
        default="RayTracedLighting",
    )
    parser.add_argument("--frame-count", type=int, default=3)
    parser.add_argument("--segment-frames", type=int, default=2)
    args = parser.parse_args(argv)

    fish_stage = {
        "appliedSchemas": ["OmniLensDistortionOpenCvFisheyeAPI"],
        "omni:lensdistortion:model": "opencvFisheye",
        "omni:lensdistortion:opencvFisheye:imageSize": [320, 240],
    }
    project = ProjectDefinition(
        project_id=args.job_id,
        name=f"v04.3 heterogeneous sensor smoke {args.renderer}",
        stage=StageReference(args.stage),
        sensors=[
            SensorDefinition(
                sensor_id="pinhole",
                plugin="pinhole_camera",
                prim_path="/World/Sensors/Pinhole",
            ),
            SensorDefinition(
                sensor_id="fisheye",
                plugin="fisheye_camera",
                prim_path="/World/Sensors/Fisheye",
                stage_parameters=dict(fish_stage),
                parameters=dict(fish_stage),
                parameter_sources={name: "stage" for name in fish_stage},
            ),
            SensorDefinition(
                sensor_id="lidar",
                plugin="rtx_lidar",
                prim_path="/World/Sensors/Lidar",
            ),
        ],
        rigs=[
            RigDefinition(
                rig_id="camera_rig",
                sensor_ids=["pinhole", "fisheye"],
                reference_frame_prim_path="/World/Sensors",
            )
        ],
        variants=[
            VariantDefinition(
                variant_id="full_scene",
                strategy="full_scene",
                modalities_by_sensor={
                    "pinhole": ["rgb"],
                    "fisheye": ["rgb", "depth_linear", "depth_color"],
                    "lidar": ["point_cloud", "point_cloud_ply"],
                },
            )
        ],
        modalities=[
            ModalityDefinition("rgb", "rgb"),
            ModalityDefinition("depth_linear", "depth_linear"),
            ModalityDefinition("depth_color", "depth_color"),
            ModalityDefinition("point_cloud", "point_cloud"),
            ModalityDefinition("point_cloud_ply", "point_cloud_ply"),
        ],
        render=RenderProfile(
            renderer=args.renderer,
            resolution_width=320,
            resolution_height=240,
            warmup_frames=6,
            rt_subframes=1,
            spp_per_frame=1,
            total_spp=1,
            max_bounces=2,
        ),
        capture=CaptureSchedule(
            physics_hz=60,
            capture_fps=10,
            start_frame=0,
            frame_count=args.frame_count,
            capture_initial_frame=False,
            segment_frames=args.segment_frames,
        ),
        output=OutputPolicy(root_dir=args.output_root),
        execution=ExecutionPolicy(
            segmentation_strategy="auto",
            heartbeat_timeout_seconds=180,
            no_progress_timeout_seconds=600,
            segment_start_timeout_seconds=300,
            graceful_stop_timeout_seconds=30,
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
