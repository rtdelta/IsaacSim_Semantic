"""Command-line entry point for one complete headless v04 JobSpec."""

import argparse
import json
import signal
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional

from semantic_world_v04.compiler import JobCompiler, ProjectValidator, SegmentPlanner
from semantic_world_v04.compiler.job_compiler import utc_now
from semantic_world_v04.core.models import JobSpec, JobStatus, SegmentSpec, SegmentStatus
from semantic_world_v04.core.progress import capture_group_count
from semantic_world_v04.output import (
    SegmentStatusStore,
    StatusStore,
    inspect_segment_completion,
)
from semantic_world_v04.output.io import atomic_write_json, read_json
from semantic_world_v04.project.paths import ProjectPathResolver
from semantic_world_v04.supervisor import GpuLock

from .bootstrap import SimulationRuntime
from .coordinator import CaptureCancelled, CaptureCoordinator
from .preflight import check_host_preflight

_cancel_requested = False
_segment_status_lock = threading.Lock()


def _request_cancel(signum, frame) -> None:
    global _cancel_requested
    _ = signum, frame
    _cancel_requested = True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one immutable Semantic World v04 JobSpec"
    )
    parser.add_argument("--job-spec", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--gpu-lock", required=True)
    parser.add_argument("--segment-spec")
    return parser


def _ensure_status(store: StatusStore, job_spec: JobSpec) -> JobStatus:
    if store.exists():
        return store.read()
    now = utc_now()
    status = JobStatus(
        job_id=job_spec.job_id,
        state="preflight",
        created_at_utc=now,
        updated_at_utc=now,
        frame_total=capture_group_count(job_spec.project),
        message="Runtime invoked directly",
    )
    store.write(status)
    return status


def _update_status(
    store: StatusStore,
    *,
    state: Optional[str] = None,
    message: Optional[str] = None,
    exit_code: Optional[int] = None,
    terminal: bool = False,
) -> JobStatus:
    status = store.read()
    now = utc_now()
    if state is not None:
        status.state = state
    if message is not None:
        status.message = message
    if exit_code is not None:
        status.exit_code = exit_code
    status.updated_at_utc = now
    status.last_heartbeat_utc = now
    if terminal:
        status.completed_at_utc = now
    store.write(status)
    return status


def _preflight(job_spec: JobSpec) -> None:
    if not JobCompiler.verify(job_spec):
        raise ValueError("JobSpec content digest does not match its payload")
    issues = [
        issue
        for issue in ProjectValidator().validate(job_spec.project)
        if issue.severity == "error"
    ]
    if issues:
        raise ValueError(
            "static validation failed: " + "; ".join(str(issue) for issue in issues)
        )
    stage_path = job_spec.project.stage.usd_path
    if job_spec.source_project_path:
        stage_path = str(
            ProjectPathResolver.resolve(
                stage_path, Path(job_spec.source_project_path)
            )
        )
    if not ProjectPathResolver.is_uri(stage_path) and not Path(stage_path).is_file():
        raise FileNotFoundError(f"USD Stage does not exist: {stage_path}")


def _load_segment(args: argparse.Namespace, job_spec: JobSpec) -> Optional[SegmentSpec]:
    if not args.segment_spec:
        return None
    segment = SegmentSpec.from_dict(read_json(Path(args.segment_spec)))
    if segment.job_id != job_spec.job_id:
        raise ValueError("SegmentSpec job_id does not match JobSpec")
    if segment.job_content_digest != job_spec.content_digest:
        raise ValueError("SegmentSpec digest does not match JobSpec")
    if segment.end_frame_exclusive != segment.start_frame + segment.frame_count:
        raise ValueError("SegmentSpec frame range is inconsistent")
    capture = job_spec.project.capture
    if segment.start_frame < capture.start_frame or segment.end_frame_exclusive > (
        capture.start_frame + capture.frame_count
    ):
        raise ValueError("SegmentSpec falls outside the JobSpec capture range")
    planned = {
        item.segment_id: item for item in SegmentPlanner().plan(job_spec)
    }.get(segment.segment_id)
    if planned is None or segment != planned:
        raise ValueError("SegmentSpec differs from the deterministic segment plan")
    return segment


def _ensure_segment_status(
    store: SegmentStatusStore, job_spec: JobSpec, segment: SegmentSpec
) -> SegmentStatus:
    if store.exists():
        return store.read()
    now = utc_now()
    status = SegmentStatus(
        job_id=job_spec.job_id,
        segment_id=segment.segment_id,
        state="starting",
        created_at_utc=now,
        updated_at_utc=now,
        capture_groups_total=segment.expected_capture_groups,
        message="Segment Runtime invoked directly",
    )
    store.write(status)
    return status


def _update_segment_status(
    store: SegmentStatusStore,
    *,
    state: Optional[str] = None,
    message: Optional[str] = None,
    exit_code: Optional[int] = None,
    failure_code: Optional[str] = None,
    committed: Optional[int] = None,
    terminal: bool = False,
) -> SegmentStatus:
    with _segment_status_lock:
        status = store.read()
        now = utc_now()
        if state is not None:
            status.state = state
        if message is not None:
            status.message = message
        if exit_code is not None:
            status.exit_code = exit_code
        if failure_code is not None:
            status.failure_code = failure_code
        if committed is not None:
            status.capture_groups_current = committed
            status.last_commit_utc = now
        status.updated_at_utc = now
        status.last_heartbeat_utc = now
        if terminal:
            status.completed_at_utc = now
        store.write(status)
        return status


def _heartbeat_loop(
    store: SegmentStatusStore, stop_event: threading.Event, interval: float
) -> None:
    while not stop_event.wait(interval):
        try:
            _update_segment_status(store)
        except Exception:
            traceback.print_exc()


def run(args: argparse.Namespace) -> int:
    job_spec = JobSpec.from_dict(read_json(Path(args.job_spec)))
    segment = _load_segment(args, job_spec)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_store = None
    segment_store = None
    if segment is None:
        status_store = StatusStore(output_dir / "status.json")
        status = _ensure_status(status_store, job_spec)
        status.frame_total = capture_group_count(job_spec.project)
        status_store.write(status)
        diagnostics_dir = output_dir
    else:
        diagnostics_dir = output_dir / "segments" / segment.segment_id
        segment_store = SegmentStatusStore(diagnostics_dir / "status.json")
        _ensure_segment_status(segment_store, job_spec, segment)
    atomic_write_json(output_dir / "job_spec.json", job_spec.to_dict())

    runtime = SimulationRuntime(job_spec)
    coordinator = None
    heartbeat_stop = None
    heartbeat_thread = None
    if segment_store is not None:
        heartbeat_stop = threading.Event()
        heartbeat_interval = max(
            1.0,
            min(5.0, job_spec.project.execution.heartbeat_timeout_seconds / 3.0),
        )
        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            args=(segment_store, heartbeat_stop, heartbeat_interval),
            name="v04-segment-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
    try:
        with GpuLock(Path(args.gpu_lock), blocking=False):
            if segment_store is not None:
                _update_segment_status(
                    segment_store,
                    state="starting",
                    message="Validating SegmentSpec and runtime inputs",
                )
            else:
                _update_status(
                    status_store,
                    state="preflight",
                    message="Validating JobSpec and runtime inputs",
                )
            _preflight(job_spec)
            host_snapshot = check_host_preflight(output_dir)
            atomic_write_json(
                diagnostics_dir / "host_preflight_snapshot.json", host_snapshot
            )
            if segment_store is not None:
                _update_segment_status(
                    segment_store,
                    state="starting",
                    message="Starting headless SimulationApp",
                )
            else:
                _update_status(
                    status_store,
                    state="preflight",
                    message="Starting headless SimulationApp",
                )
            runtime.start()
            if segment_store is not None:
                _update_segment_status(
                    segment_store, state="starting", message="Opening USD Stage"
                )
            else:
                _update_status(
                    status_store, state="preflight", message="Opening USD Stage"
                )
            runtime.open_stage()
            render_snapshot = runtime.apply_render_settings()
            atomic_write_json(
                diagnostics_dir / "runtime_snapshot.json", render_snapshot
            )
            if segment_store is not None:
                _update_segment_status(
                    segment_store,
                    state="running",
                    message="Initializing sensors and capture coordinator",
                )
            else:
                _update_status(
                    status_store,
                    state="running",
                    message="Initializing sensors and capture coordinator",
                )

            def segment_progress(message: str, committed: int) -> None:
                assert segment_store is not None
                _update_segment_status(
                    segment_store,
                    state="running",
                    message=message,
                    committed=committed,
                )

            coordinator = CaptureCoordinator(
                job_spec=job_spec,
                runtime=runtime,
                output_dir=output_dir,
                status_store=status_store,
                cancelled=lambda: _cancel_requested,
                segment_spec=segment,
                progress_callback=(
                    segment_progress if segment_store is not None else None
                ),
            )
            coordinator.run()
            if segment_store is not None:
                completion = inspect_segment_completion(
                    output_dir, job_spec.project, segment
                )
                if not completion.complete:
                    raise RuntimeError(
                        "Segment exited without all capture groups: "
                        f"{completion.committed}/{completion.expected}"
                    )
                _update_segment_status(
                    segment_store,
                    state="completed",
                    message="Segment capture completed",
                    exit_code=0,
                    committed=completion.committed,
                    terminal=True,
                )
            else:
                _update_status(
                    status_store,
                    state="completed",
                    message="Capture completed",
                    exit_code=0,
                    terminal=True,
                )
            return 0
    except CaptureCancelled as exc:
        if segment_store is not None:
            _update_segment_status(
                segment_store,
                state="cancelled",
                message=str(exc),
                exit_code=0,
                terminal=True,
            )
        else:
            _update_status(
                status_store,
                state="cancelled",
                message=str(exc),
                exit_code=0,
                terminal=True,
            )
        return 0
    except BaseException as exc:
        traceback.print_exc()
        if segment_store is not None:
            _update_segment_status(
                segment_store,
                state="failed",
                message=f"{type(exc).__name__}: {exc}",
                exit_code=1,
                failure_code=type(exc).__name__,
                terminal=True,
            )
        elif status_store is not None:
            _update_status(
                status_store,
                state="failed",
                message=f"{type(exc).__name__}: {exc}",
                exit_code=1,
                terminal=True,
            )
        return 1
    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2.0)
        if coordinator is not None:
            try:
                coordinator.close()
            except BaseException:
                traceback.print_exc()
        runtime.close()


def main(argv=None) -> int:
    signal.signal(signal.SIGTERM, _request_cancel)
    signal.signal(signal.SIGINT, _request_cancel)
    args = _parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
