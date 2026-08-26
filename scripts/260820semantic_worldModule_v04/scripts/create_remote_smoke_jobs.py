"""Create self-contained v04 smoke projects and immutable JobSpecs."""

import argparse
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler
from semantic_world_v04.core.models import (
    CaptureSchedule,
    ModalityDefinition,
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
    parser.add_argument(
        "--stage",
        default=(
            "/root/gpufree-data/IsaacSim_Asset/combine_stage/"
            "combine_scene_05.usda"
        ),
    )
    parser.add_argument(
        "--camera",
        default="/Excavator_Fangshan_03/boom_prim/Camera",
    )
    return parser


def build_project(
    *,
    project_id: str,
    renderer: str,
    stage: str,
    camera: str,
    output_root: str,
) -> ProjectDefinition:
    return ProjectDefinition(
        project_id=project_id,
        name=f"v04 {renderer} smoke",
        stage=StageReference(stage),
        sensors=[
            SensorDefinition(
                sensor_id="boom_camera",
                plugin="pinhole_camera",
                prim_path=camera,
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
            renderer=renderer,
            resolution_width=320,
            resolution_height=180,
            warmup_frames=4,
            rt_subframes=1,
            spp_per_frame=1,
            total_spp=1,
            max_bounces=2,
            denoiser=True,
        ),
        capture=CaptureSchedule(
            physics_hz=60,
            capture_fps=10,
            start_frame=0,
            frame_count=1,
            capture_initial_frame=True,
            segment_frames=1,
        ),
        output=OutputPolicy(root_dir=output_root),
    )


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    workspace = Path(args.workspace)
    repository = ProjectRepository()
    compiler = JobCompiler()
    for suffix, renderer in (
        ("realtime", "RayTracedLighting"),
        ("pathtracing", "PathTracing"),
    ):
        project_dir = workspace / f"v04_smoke_{suffix}.swproject"
        job_id = f"job-v04-{suffix}-smoke"
        project = build_project(
            project_id=f"v04-smoke-{suffix}",
            renderer=renderer,
            stage=args.stage,
            camera=args.camera,
            output_root=args.output_root,
        )
        repository.save(project_dir, project)
        job = compiler.compile(
            project,
            source_project_path=project_dir.as_posix(),
            job_id=job_id,
        )
        job_path = project_dir / "jobs" / job.job_id / "job_spec.json"
        atomic_write_json(job_path, job.to_dict())
        print(f"{suffix}={job_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
