"""Create a one-frame v04.4 production-preset UI workflow smoke job."""

import argparse
from pathlib import Path

from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.stage import PrimSummary, StageIndex
from semantic_world_v04.studio import StudioController


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--excavator", required=True)
    parser.add_argument("--light", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)

    controller = StudioController()
    controller.new_project(
        project_id=args.job_id,
        name="v04.4 Studio UX production-preset smoke",
        usd_path=args.stage,
        output_root=args.output_root,
    )
    controller.set_stage_index(
        StageIndex(
            [
                PrimSummary("/", "PseudoRoot"),
                PrimSummary(args.excavator, "Xform"),
                PrimSummary(args.camera, "Camera"),
                PrimSummary(args.light, "DistantLight"),
            ],
            stage_identifier=args.stage,
        )
    )
    sensor = controller.set_stage_sensor_selected(args.camera, True)
    variant = controller.create_isolate_variant(
        [args.excavator], preserve_lights=True
    )
    controller.apply_modality_preset(
        "full_scene", sensor.sensor_id, "common_all"
    )
    controller.apply_modality_preset(
        variant.variant_id, sensor.sensor_id, "common_all"
    )
    controller.set_capture_schedule(
        physics_hz=60,
        capture_fps=10,
        start_frame=0,
        frame_count=1,
        capture_initial_frame=False,
        segment_frames=1,
    )

    project_dir = Path(args.workspace) / f"{args.job_id}.swproject"
    controller.save_project(project_dir)
    job = controller.compile_job(job_id=args.job_id)
    job_path = project_dir / "jobs" / job.job_id / "job_spec.json"
    atomic_write_json(job_path, job.to_dict())
    print(job_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
