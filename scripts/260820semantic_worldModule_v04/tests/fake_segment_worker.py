"""Process-level fake used by JobRunner tests; it does not import Kit/Isaac."""

import argparse
import os
import sys
import time
from pathlib import Path

from semantic_world_v04.compiler.job_compiler import utc_now
from semantic_world_v04.core.models import JobSpec, SegmentSpec
from semantic_world_v04.core.progress import expected_capture_keys
from semantic_world_v04.output import (
    AtomicFrameWriter,
    FrameLedger,
    SegmentStatusStore,
)
from semantic_world_v04.output.io import read_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-spec", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--gpu-lock", required=True)
    parser.add_argument("--segment-spec", required=True)
    args = parser.parse_args()
    _ = args.gpu_lock
    job = JobSpec.from_dict(read_json(Path(args.job_spec)))
    segment = SegmentSpec.from_dict(read_json(Path(args.segment_spec)))
    output = Path(args.output_dir)
    segment_dir = output / "segments" / segment.segment_id
    (segment_dir / "fake_worker.marker").write_text("started\n", encoding="utf-8")
    store = SegmentStatusStore(segment_dir / "status.json")
    status = store.read()
    status.state = "running"
    status.updated_at_utc = utc_now()
    status.last_heartbeat_utc = status.updated_at_utc
    status.message = "Fake worker running"
    store.write(status)
    failure_mode = os.environ.get("V04_FAKE_WORKER_MODE")
    if failure_mode in {"fail", "fail_zero"}:
        status = store.read()
        status.state = "failed"
        status.exit_code = 7
        status.failure_code = "injected_failure"
        status.message = "Injected fake worker failure"
        status.updated_at_utc = utc_now()
        status.completed_at_utc = status.updated_at_utc
        store.write(status)
        return 0 if failure_mode == "fail_zero" else 7

    ledger = FrameLedger(output / "ledger.jsonl")
    writer = AtomicFrameWriter(output, ledger)
    committed = 0
    delay = float(os.environ.get("V04_FAKE_WORKER_DELAY", "0"))
    for frame_index, sensor_id, variant_id in expected_capture_keys(
        job.project, segment.start_frame, segment.frame_count
    ):
        writer.commit(
            frame_index=frame_index,
            sensor_id=sensor_id,
            variant_id=variant_id,
            simulation_time=float(frame_index),
            requested_modalities=["fake"],
            artifacts={
                f"fake/{frame_index:06d}__{sensor_id}__{variant_id}.bin": b"ok"
            },
        )
        if delay > 0:
            time.sleep(delay)
        committed += 1
        status = store.read()
        status.capture_groups_current = committed
        status.last_commit_utc = utc_now()
        status.last_heartbeat_utc = status.last_commit_utc
        status.updated_at_utc = status.last_commit_utc
        store.write(status)
    status = store.read()
    status.state = "completed"
    status.exit_code = 0
    status.capture_groups_current = committed
    status.updated_at_utc = utc_now()
    status.last_heartbeat_utc = status.updated_at_utc
    status.completed_at_utc = status.updated_at_utc
    status.message = "Fake segment completed"
    store.write(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
