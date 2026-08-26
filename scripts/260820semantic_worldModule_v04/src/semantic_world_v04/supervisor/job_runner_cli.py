"""CLI entry point for one lightweight v04 Job Runner process."""

import argparse
import signal
import traceback
from pathlib import Path

from semantic_world_v04.compiler.job_compiler import utc_now
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.output.status_store import StatusStore

from .job_runner import JobRunner

_cancel_requested = False


def _request_cancel(signum, frame) -> None:
    global _cancel_requested
    _ = signum, frame
    _cancel_requested = True


def _parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Run one segmented v04 job")
    parser.add_argument("--job-spec", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--gpu-lock", required=True)
    parser.add_argument(
        "--segment-worker-command",
        default=str(project_root / "scripts" / "launch_runtime.sh"),
    )
    return parser


def main(argv=None) -> int:
    signal.signal(signal.SIGTERM, _request_cancel)
    signal.signal(signal.SIGINT, _request_cancel)
    args = _parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    try:
        runner = JobRunner(
            job_spec_path=Path(args.job_spec),
            output_dir=output_dir,
            gpu_lock_path=Path(args.gpu_lock),
            worker_command=[args.segment_worker_command],
            cancelled=lambda: _cancel_requested,
        )
        return runner.run()
    except BaseException as exc:
        details = traceback.format_exc()
        print(details, end="")
        now = utc_now()
        report_path = output_dir / "failure_report.json"
        atomic_write_json(
            report_path,
            {
                "schema_version": 1,
                "failure_code": "job_runner_exception",
                "message": str(exc),
                "created_at_utc": now,
                "traceback": details,
                "resume": {"allowed": True, "command": "supervisor resume"},
            },
        )
        status_path = output_dir / "status.json"
        if status_path.is_file():
            store = StatusStore(status_path)
            status = store.read()
            status.state = "failed"
            status.message = f"Job Runner failed: {exc}"
            status.failure_report_path = str(report_path)
            status.exit_code = 1
            status.updated_at_utc = now
            status.last_heartbeat_utc = now
            status.completed_at_utc = now
            store.write(status)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
