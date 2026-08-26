"""Structured failure reports for resumable long-running jobs."""

import platform
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from semantic_world_v04.compiler.job_compiler import utc_now
from semantic_world_v04.core.models import JobSpec, SegmentSpec, SegmentStatus
from semantic_world_v04.output.io import atomic_write_json, read_json
from semantic_world_v04.output.ledger import FrameLedger


def _tail(path: Path, lines: int = 100):
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        return [line.rstrip("\n") for line in stream.readlines()[-lines:]]


def write_failure_report(
    output_dir: Path,
    *,
    job_spec: JobSpec,
    segment: SegmentSpec,
    status: SegmentStatus,
    failure_code: str,
    message: str,
    gpu_snapshot: Optional[Dict[str, Any]] = None,
    resume_allowed: bool = True,
) -> Path:
    output_dir = Path(output_dir)
    report_path = output_dir / "failure_report.json"
    segment_dir = output_dir / "segments" / segment.segment_id
    staging = output_dir / ".staging"
    staging_entries = (
        sorted(str(path.relative_to(staging)) for path in staging.rglob("*"))
        if staging.is_dir()
        else []
    )
    last_ledger_entry = None
    for entry in FrameLedger(output_dir / "ledger.jsonl").entries():
        last_ledger_entry = entry.to_dict()
    host_snapshot_path = segment_dir / "host_preflight_snapshot.json"
    runtime_snapshot_path = segment_dir / "runtime_snapshot.json"
    host_snapshot = (
        read_json(host_snapshot_path) if host_snapshot_path.is_file() else None
    )
    runtime_snapshot = (
        read_json(runtime_snapshot_path) if runtime_snapshot_path.is_file() else None
    )
    report = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "job_id": job_spec.job_id,
        "job_content_digest": job_spec.content_digest,
        "segment_id": segment.segment_id,
        "segment_index": segment.segment_index,
        "segment_range": {
            "start_frame": segment.start_frame,
            "end_frame_exclusive": segment.end_frame_exclusive,
        },
        "failure_code": failure_code,
        "message": message,
        "segment_status": status.to_dict(),
        "last_ledger_entry": last_ledger_entry,
        "gpu_snapshot": gpu_snapshot or {},
        "host_preflight_snapshot": host_snapshot,
        "runtime_snapshot": runtime_snapshot,
        "render_profile": job_spec.project.to_dict()["render"],
        "job_runner_environment": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
        },
        "staging_entries": staging_entries,
        "runtime_log_tail": _tail(segment_dir / "runtime.log"),
        "resume_allowed": bool(resume_allowed),
        "recommended_resume_segment": segment.segment_id,
        "resume": {
            "allowed": bool(resume_allowed),
            "segment_id": segment.segment_id,
            "require_same_job_digest": True,
            "preserve_committed_capture_groups": True,
        },
    }
    atomic_write_json(report_path, report)
    return report_path
