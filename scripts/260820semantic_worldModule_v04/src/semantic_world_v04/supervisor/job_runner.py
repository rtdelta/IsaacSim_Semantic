"""Lightweight per-job orchestration of independent Isaac Segment Workers."""

import os
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

from semantic_world_v04.compiler import JobCompiler, SegmentPlanner
from semantic_world_v04.compiler.job_compiler import utc_now
from semantic_world_v04.core.models import JobSpec, JobStatus, SegmentSpec, SegmentStatus
from semantic_world_v04.output import (
    FrameLedger,
    SegmentStatusStore,
    StatusStore,
    inspect_segment_completion,
)
from semantic_world_v04.output.io import atomic_write_json, read_json

from .failure_report import write_failure_report
from .process_launcher import ProcessHandle, ProcessLauncher
from .telemetry import TelemetryRecorder
from .watchdog import SegmentWatchdog, WatchdogDecision


class JobRunner:
    def __init__(
        self,
        *,
        job_spec_path: Path,
        output_dir: Path,
        gpu_lock_path: Path,
        worker_command: Sequence[str],
        cancelled: Callable[[], bool],
        launcher: Optional[ProcessLauncher] = None,
        telemetry: Optional[TelemetryRecorder] = None,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.job_spec_path = Path(job_spec_path)
        self.output_dir = Path(output_dir)
        self.gpu_lock_path = Path(gpu_lock_path)
        self.worker_command = list(worker_command)
        self.cancelled = cancelled
        self.launcher = launcher or ProcessLauncher()
        self.telemetry = telemetry or TelemetryRecorder(self.output_dir)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.status_store = StatusStore(self.output_dir / "status.json")
        self.job_spec = JobSpec.from_dict(read_json(self.job_spec_path))
        if not JobCompiler.verify(self.job_spec):
            raise ValueError("JobSpec content digest is invalid")
        self.segments = SegmentPlanner().plan(self.job_spec)
        self.last_gpu_snapshot = {}
        self.run_started_monotonic = 0.0
        self.run_initial_committed = 0

    def run(self) -> int:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_started_monotonic = time.monotonic()
        self.run_initial_committed = len(
            list(FrameLedger(self.output_dir / "ledger.jsonl").entries())
        )
        self._persist_plan()
        self._update_job(
            state="running",
            message="Job Runner started segmented execution",
            segment_total=len(self.segments),
        )
        for segment in self.segments:
            if self.cancelled():
                self._cancel_job("Job cancellation requested before next segment")
                return 0
            completion = inspect_segment_completion(
                self.output_dir, self.job_spec.project, segment
            )
            if completion.complete:
                self._mark_existing_complete(segment, completion.committed)
                continue
            outcome = self._run_segment(segment, completion.committed)
            if outcome == "cancelled":
                self._cancel_job(f"Cancelled during {segment.segment_id}")
                return 0
            if outcome == "failed":
                return 1

        total = len(list(FrameLedger(self.output_dir / "ledger.jsonl").entries()))
        self._update_job(
            state="completed",
            message="All segments completed",
            frame_current=total,
            segment_current=len(self.segments),
            current_segment_id=(self.segments[-1].segment_id if self.segments else None),
            estimated_remaining_seconds=0.0,
            exit_code=0,
            terminal=True,
        )
        return 0

    def _persist_plan(self) -> None:
        document = SegmentPlanner().plan_document(self.job_spec)
        path = self.output_dir / "segment_plan.json"
        if path.is_file() and read_json(path) != document:
            raise ValueError("persisted segment plan differs from immutable JobSpec")
        atomic_write_json(path, document)
        for segment in self.segments:
            segment_dir = self.output_dir / "segments" / segment.segment_id
            spec_path = segment_dir / "segment_spec.json"
            if spec_path.is_file() and read_json(spec_path) != segment.to_dict():
                raise ValueError(f"persisted SegmentSpec differs: {segment.segment_id}")
            atomic_write_json(spec_path, segment.to_dict())
            store = SegmentStatusStore(segment_dir / "status.json")
            if not store.exists():
                now = utc_now()
                store.write(
                    SegmentStatus(
                        job_id=self.job_spec.job_id,
                        segment_id=segment.segment_id,
                        state="planned",
                        created_at_utc=now,
                        updated_at_utc=now,
                        capture_groups_total=segment.expected_capture_groups,
                        message="Segment planned",
                    )
                )

    def _run_segment(self, segment: SegmentSpec, committed: int) -> str:
        segment_dir = self.output_dir / "segments" / segment.segment_id
        store = SegmentStatusStore(segment_dir / "status.json")
        argv = [
            *self.worker_command,
            "--job-spec",
            str(self.job_spec_path),
            "--output-dir",
            str(self.output_dir),
            "--gpu-lock",
            str(self.gpu_lock_path),
            "--segment-spec",
            str(segment_dir / "segment_spec.json"),
        ]
        project_root = Path(__file__).resolve().parents[3]
        python_path = str(project_root / "src")
        inherited_python_path = os.environ.get("PYTHONPATH")
        if inherited_python_path:
            python_path = python_path + os.pathsep + inherited_python_path
        handle = self.launcher.launch(
            argv,
            log_path=segment_dir / "runtime.log",
            cwd=project_root,
            env={
                **os.environ,
                "SEMANTIC_WORLD_RUNTIME_ROOT": str(segment_dir / ".runtime"),
                "PYTHONPATH": python_path,
            },
        )
        now = utc_now()
        status = store.read()
        status.state = "starting"
        status.pid = handle.pid
        status.process_token = handle.token
        status.started_at_utc = now
        status.completed_at_utc = None
        status.exit_code = None
        status.failure_code = None
        status.updated_at_utc = now
        status.last_heartbeat_utc = now
        status.capture_groups_current = committed
        status.message = "Segment Worker launched"
        store.write(status)
        started = time.monotonic()
        watchdog = SegmentWatchdog(self.job_spec.project.execution, started)
        last_sample = 0.0
        while True:
            now_monotonic = time.monotonic()
            exit_code = handle.process.poll()
            process_alive = exit_code is None
            status = store.read()
            self._refresh_job_progress(segment, status)
            if self.cancelled():
                self._terminate_worker(handle)
                refreshed = store.read()
                if refreshed.state not in {"cancelled", "completed"}:
                    self._set_segment_terminal(
                        store,
                        refreshed,
                        state="cancelled",
                        exit_code=handle.process.poll(),
                        failure_code=None,
                        message="Job Runner stopped Segment Worker",
                    )
                return "cancelled"
            if now_monotonic - last_sample >= self.job_spec.project.execution.telemetry_interval_seconds:
                self.last_gpu_snapshot = self.telemetry.sample_gpu(
                    segment_id=segment.segment_id, worker_pid=handle.pid
                )
                self.telemetry.progress(
                    {
                        "job_id": self.job_spec.job_id,
                        "segment_id": segment.segment_id,
                        "segment_index": segment.segment_index,
                        "capture_groups_current": status.capture_groups_current,
                        "capture_groups_total": status.capture_groups_total,
                    }
                )
                last_sample = now_monotonic
            heartbeat_age = self._status_file_age(store)
            decision = watchdog.observe(
                status,
                now_monotonic=now_monotonic,
                process_alive=process_alive,
                heartbeat_age_seconds=heartbeat_age,
            )
            if decision is not None:
                self._terminate_worker(handle)
                self._fail_segment(segment, store, decision, handle.process.poll())
                return "failed"
            if exit_code is not None:
                handle.log_stream.close()
                refreshed = store.read()
                completion = inspect_segment_completion(
                    self.output_dir, self.job_spec.project, segment
                )
                if exit_code == 0 and completion.complete:
                    if refreshed.state != "completed":
                        self._set_segment_terminal(
                            store,
                            refreshed,
                            state="completed",
                            exit_code=0,
                            failure_code=None,
                            message=(
                                "Segment completion verified from Ledger after "
                                "successful Worker exit"
                            ),
                            committed=completion.committed,
                        )
                    self.telemetry.segment_timing(
                        {
                            "job_id": self.job_spec.job_id,
                            "segment_id": segment.segment_id,
                            "duration_seconds": now_monotonic - started,
                            "capture_groups": completion.committed,
                            "state": "completed",
                        }
                    )
                    return "completed"
                if refreshed.state == "cancelled" and self.cancelled():
                    return "cancelled"
                decision = WatchdogDecision(
                    refreshed.failure_code or "segment_worker_exit",
                    (
                        f"Segment Worker exited with code {exit_code}; "
                        f"state={refreshed.state}; "
                        f"committed={completion.committed}/{completion.expected}"
                    ),
                )
                self._fail_segment(segment, store, decision, exit_code)
                return "failed"
            time.sleep(self.poll_interval_seconds)

    def _refresh_job_progress(
        self, segment: SegmentSpec, segment_status: SegmentStatus
    ) -> None:
        total = len(list(FrameLedger(self.output_dir / "ledger.jsonl").entries()))
        gpu_memory = None
        devices = self.last_gpu_snapshot.get("devices", [])
        if devices:
            gpu_memory = devices[0].get("memory_used_mb")
        status = self.status_store.read()
        elapsed = max(0.0, time.monotonic() - self.run_started_monotonic)
        completed_this_run = max(0, total - self.run_initial_committed)
        estimated_remaining = None
        if completed_this_run > 0 and elapsed > 0 and status.frame_total > total:
            groups_per_second = completed_this_run / elapsed
            estimated_remaining = (status.frame_total - total) / groups_per_second
        self._update_job(
            state="running",
            message=segment_status.message,
            frame_current=total,
            segment_current=segment.segment_index + 1,
            segment_total=len(self.segments),
            current_segment_id=segment.segment_id,
            last_commit_utc=segment_status.last_commit_utc,
            gpu_memory_used_mb=gpu_memory,
            estimated_remaining_seconds=estimated_remaining,
        )

    def _mark_existing_complete(self, segment: SegmentSpec, committed: int) -> None:
        store = SegmentStatusStore(
            self.output_dir / "segments" / segment.segment_id / "status.json"
        )
        status = store.read()
        if status.state != "completed":
            self._set_segment_terminal(
                store,
                status,
                state="completed",
                exit_code=0,
                failure_code=None,
                message="Segment already complete according to Ledger",
                committed=committed,
            )
        self._update_job(
            state="running",
            message=f"Verified completed {segment.segment_id}",
            segment_current=segment.segment_index + 1,
            segment_total=len(self.segments),
            current_segment_id=segment.segment_id,
        )

    def _fail_segment(
        self,
        segment: SegmentSpec,
        store: SegmentStatusStore,
        decision: WatchdogDecision,
        exit_code: Optional[int],
    ) -> None:
        # Some Isaac launcher builds mask the Python SystemExit value and
        # return zero even though the Worker persisted state=failed.  A failed
        # segment must never surface as a successful process result.
        failure_exit_code = exit_code if exit_code not in (None, 0) else 1
        status = store.read()
        self._set_segment_terminal(
            store,
            status,
            state="failed",
            exit_code=failure_exit_code,
            failure_code=decision.failure_code,
            message=decision.message,
        )
        report_path = write_failure_report(
            self.output_dir,
            job_spec=self.job_spec,
            segment=segment,
            status=store.read(),
            failure_code=decision.failure_code,
            message=decision.message,
            gpu_snapshot=self.last_gpu_snapshot,
            resume_allowed=True,
        )
        self._update_job(
            state="failed",
            message=decision.message,
            exit_code=failure_exit_code,
            failure_report_path=str(report_path),
            terminal=True,
        )

    def _terminate_worker(self, handle: ProcessHandle) -> None:
        if handle.process.poll() is not None:
            handle.log_stream.close()
            return
        self.launcher.terminate(handle.pid, handle.token)
        deadline = time.monotonic() + self.job_spec.project.execution.graceful_stop_timeout_seconds
        while handle.process.poll() is None and time.monotonic() < deadline:
            time.sleep(min(self.poll_interval_seconds, 0.1))
        if handle.process.poll() is None:
            self.launcher.kill(handle.pid, handle.token)
        try:
            handle.process.wait(timeout=5)
        except Exception:
            pass
        handle.log_stream.close()

    @staticmethod
    def _set_segment_terminal(
        store: SegmentStatusStore,
        status: SegmentStatus,
        *,
        state: str,
        exit_code: Optional[int],
        failure_code: Optional[str],
        message: str,
        committed: Optional[int] = None,
    ) -> None:
        now = utc_now()
        status.state = state
        status.exit_code = exit_code
        status.failure_code = failure_code
        status.message = message
        status.updated_at_utc = now
        status.last_heartbeat_utc = now
        status.completed_at_utc = now
        if committed is not None:
            status.capture_groups_current = committed
        store.write(status)

    def _cancel_job(self, message: str) -> None:
        self._update_job(
            state="cancelled",
            message=message,
            exit_code=0,
            terminal=True,
        )

    def _update_job(
        self,
        *,
        state: Optional[str] = None,
        message: Optional[str] = None,
        frame_current: Optional[int] = None,
        segment_current: Optional[int] = None,
        segment_total: Optional[int] = None,
        current_segment_id: Optional[str] = None,
        last_commit_utc: Optional[str] = None,
        gpu_memory_used_mb: Optional[int] = None,
        estimated_remaining_seconds: Optional[float] = None,
        failure_report_path: Optional[str] = None,
        exit_code: Optional[int] = None,
        terminal: bool = False,
    ) -> JobStatus:
        status = self.status_store.read()
        now = utc_now()
        if state is not None:
            status.state = state
        if message is not None:
            status.message = message
        if frame_current is not None:
            status.frame_current = frame_current
        if segment_current is not None:
            status.segment_current = segment_current
        if segment_total is not None:
            status.segment_total = segment_total
        if current_segment_id is not None:
            status.current_segment_id = current_segment_id
        if last_commit_utc is not None:
            status.last_commit_utc = last_commit_utc
        if gpu_memory_used_mb is not None:
            status.gpu_memory_used_mb = gpu_memory_used_mb
        if estimated_remaining_seconds is not None:
            status.estimated_remaining_seconds = estimated_remaining_seconds
        if failure_report_path is not None:
            status.failure_report_path = failure_report_path
        if exit_code is not None:
            status.exit_code = exit_code
        status.updated_at_utc = now
        status.last_heartbeat_utc = now
        if terminal:
            status.completed_at_utc = now
        self.status_store.write(status)
        return status

    @staticmethod
    def _status_file_age(store: SegmentStatusStore) -> float:
        try:
            return max(0.0, time.time() - store.path.stat().st_mtime)
        except OSError:
            return float("inf")
