"""Validate one completed v04 dataset from JobSpec, Ledger and file headers."""

import argparse
import json
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler, SegmentPlanner
from semantic_world_v04.core.models import JobSpec, JobStatus
from semantic_world_v04.core.sensor_models import CaptureBatchKey
from semantic_world_v04.core.progress import expected_capture_keys
from semantic_world_v04.output import (
    AtomicCaptureBatchWriter,
    AtomicFrameWriter,
    BatchLedger,
    FrameLedger,
    validate_artifact_file,
)
from semantic_world_v04.output.io import read_json
from semantic_world_v04.plugins import build_default_registry


def validate(job_dir: Path) -> dict:
    job_dir = Path(job_dir)
    job = JobSpec.from_dict(read_json(job_dir / "job_spec.json"))
    if not JobCompiler.verify(job):
        raise ValueError("JobSpec digest is invalid")
    status = JobStatus.from_dict(read_json(job_dir / "status.json"))
    if status.state != "completed":
        raise ValueError(f"job is not completed: {status.state}")

    capture = job.project.capture
    expected_keys = expected_capture_keys(
        job.project, capture.start_frame, capture.frame_count
    )
    ledger = FrameLedger(job_dir / "ledger.jsonl")
    entries = list(ledger.entries())
    if len(entries) != len(expected_keys):
        raise ValueError(
            f"ledger count mismatch: {len(entries)}/{len(expected_keys)}"
        )
    writer = AtomicFrameWriter(job_dir, ledger)
    for key in expected_keys:
        if not writer.is_committed(*key):
            raise ValueError(f"capture group is not committed: {key}")

    width = job.project.render.resolution_width
    height = job.project.render.resolution_height
    registry = build_default_registry()
    modality_by_id = {
        modality.modality_id: modality
        for modality in job.project.modalities
        if modality.enabled
    }
    sensor_by_id = {
        sensor.sensor_id: sensor for sensor in job.project.sensors if sensor.enabled
    }
    artifact_count = 0
    for entry in entries:
        values = set(entry.files.values())
        expected_suffixes = {f"/metadata/{entry.frame_index:06d}.json"}
        for modality_id in entry.requested_modalities:
            definition = modality_by_id[modality_id]
            plugin = registry.modality(definition.plugin)
            expected_suffixes.add(
                f"/{modality_id}/{entry.frame_index:06d}{plugin.output_extension}"
            )
        for suffix in expected_suffixes:
            if not any(value.endswith(suffix) for value in values):
                raise ValueError(
                    f"capture group is missing {suffix}: "
                    f"{entry.frame_index}/{entry.sensor_id}/{entry.variant_id}"
                )
        for relative in values:
            path = job_dir / relative
            artifact_count += 1
            modality_id = next(
                (
                    modality
                    for modality in entry.requested_modalities
                    if f"/{modality}/" in relative
                ),
                None,
            )
            if modality_id is not None:
                sensor = sensor_by_id[entry.sensor_id]
                resolution = sensor.parameters.get("resolution", [width, height])
                expected_resolution = None
                if sensor.plugin in {"pinhole_camera", "fisheye_camera"}:
                    expected_resolution = (int(resolution[0]), int(resolution[1]))
                validate_artifact_file(
                    modality_id,
                    path,
                    expected_resolution=expected_resolution,
                )
            elif path.suffix == ".json":
                with path.open("r", encoding="utf-8") as stream:
                    json.load(stream)

    batch_count = 0
    batch_path = job_dir / "batch_ledger.jsonl"
    if batch_path.is_file():
        batch_ledger = BatchLedger(batch_path)
        batch_entries = list(batch_ledger.entries())
        batch_writer = AtomicCaptureBatchWriter(
            job_dir, ledger, batch_ledger
        )
        for batch in batch_entries:
            if not batch_writer.is_committed(
                CaptureBatchKey(
                    frame_index=batch.frame_index,
                    variant_id=batch.variant_id,
                    sync_group_id=batch.sync_group_id,
                )
            ):
                raise ValueError(f"capture batch is not committed: {batch}")
        batch_count = len(batch_entries)

    for sensor in sensor_by_id.values():
        if sensor.plugin_version:
            calibration = job_dir / "calibrations" / f"{sensor.sensor_id}.json"
            if not calibration.is_file():
                raise ValueError(f"sensor calibration snapshot is missing: {calibration}")
            read_json(calibration)

    segments = SegmentPlanner().plan(job)
    for segment in segments:
        snapshot = read_json(
            job_dir / "segments" / segment.segment_id / "runtime_snapshot.json"
        )
        if snapshot.get("renderer") != job.project.render.renderer:
            raise ValueError(f"renderer readback mismatch: {segment.segment_id}")

    return {
        "valid": True,
        "job_id": job.job_id,
        "renderer": job.project.render.renderer,
        "resolution": [width, height],
        "capture_groups": len(entries),
        "artifacts": artifact_count,
        "capture_batches": batch_count,
        "segments": len(segments),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_dir")
    args = parser.parse_args(argv)
    print(json.dumps(validate(Path(args.job_dir)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
