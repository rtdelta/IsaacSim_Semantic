"""External worker supervisor with segmentation, heartbeat timeout, and resume."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import RunConfig
from .errors import ResumeError, WorkerTerminationError, WorkerTimeoutError
from .heartbeat import phase_timeout, read_heartbeat
from .ledger import CommitLedger


@dataclass(frozen=True)
class Segment:
    segment_id: str
    start_frame: int
    end_frame: int
    variant_id: str


def plan_segments(config: RunConfig) -> tuple[Segment, ...]:
    result: list[Segment] = []
    variants: Iterable[str]
    if config.capture.variant_execution == "variant_major":
        variants = (item.variant_id for item in config.capture.variants)
    else:
        variants = ("all_variants",)
    for variant_id in variants:
        for start in range(0, config.capture.frames, config.runtime.segment_frames):
            end = min(config.capture.frames, start + config.runtime.segment_frames)
            result.append(
                Segment(
                    segment_id=f"{variant_id}-{start:08d}-{end:08d}",
                    start_frame=start,
                    end_frame=end,
                    variant_id=variant_id,
                )
            )
    return tuple(result)


def _segment_complete(segment: Segment, config: RunConfig, ledger: CommitLedger) -> bool:
    variants = (
        [segment.variant_id]
        if config.capture.variant_execution == "variant_major"
        else [item.variant_id for item in config.capture.variants]
    )
    return all(
        ledger.contains(variant_id, frame_id)
        for variant_id in variants
        for frame_id in range(segment.start_frame, segment.end_frame)
    )


def _terminate(process: subprocess.Popen[bytes], timeout: float) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=timeout)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            try:
                process.wait(timeout=max(1.0, timeout))
            except subprocess.TimeoutExpired as exc:
                raise WorkerTerminationError(
                    f"Worker process {process.pid} remained alive after SIGKILL/kill"
                ) from exc


class Supervisor:
    def __init__(self, config: RunConfig, *, headless: bool = True) -> None:
        self.config = config
        self.headless = headless
        self.ledger = CommitLedger(
            config.output, run_id=config.run_id, fingerprint=config.fingerprint
        )
        if not config.runtime.resume and self.ledger.committed_keys():
            raise ResumeError("Output already has committed frames and runtime.resume is false")
        self.meta_root = Path(config.output) / ".v03"
        self.log_root = self.meta_root / "logs"
        self.heartbeat_root = self.meta_root / "heartbeats"
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.heartbeat_root.mkdir(parents=True, exist_ok=True)

    def _command(self, segment: Segment, heartbeat: Path) -> list[str]:
        prefix = list(self.config.runtime.worker_command) or [sys.executable]
        command = [
            *prefix,
            "-m",
            "semantic_world_v03.worker",
            "--config",
            str(self.config.source_path),
            "--segment-id",
            segment.segment_id,
            "--start-frame",
            str(segment.start_frame),
            "--end-frame",
            str(segment.end_frame),
            "--variant",
            segment.variant_id,
            "--heartbeat",
            str(heartbeat),
            "--headless" if self.headless else "--no-headless",
        ]
        return command

    def _run_attempt(self, segment: Segment, attempt: int) -> None:
        heartbeat_path = self.heartbeat_root / f"{segment.segment_id}.json"
        log_path = self.log_root / (
            f"{segment.segment_id}.attempt-{attempt}.supervisor-{os.getpid()}.log"
        )
        command = self._command(segment, heartbeat_path)
        heartbeat_path.unlink(missing_ok=True)
        launch_time = time.time()
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parent.parent),
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            try:
                while process.poll() is None:
                    heartbeat = read_heartbeat(heartbeat_path)
                    if heartbeat is None:
                        age = time.time() - launch_time
                        timeout = self.config.runtime.startup_timeout_seconds
                        phase = "not_started"
                    else:
                        age = time.time() - float(heartbeat.get("updated_unix", 0.0))
                        phase = str(heartbeat.get("phase", "unknown"))
                        timeout = phase_timeout(
                            phase,
                            startup=self.config.runtime.startup_timeout_seconds,
                            render=self.config.runtime.render_timeout_seconds,
                            shutdown=self.config.runtime.shutdown_timeout_seconds,
                        )
                    if age > timeout:
                        raise WorkerTimeoutError(
                            f"Worker {segment.segment_id} heartbeat phase={phase} stale for {age:.1f}s"
                        )
                    time.sleep(self.config.runtime.poll_seconds)
                if process.returncode != 0:
                    raise RuntimeError(
                        f"Worker {segment.segment_id} exited with code {process.returncode}; log={log_path}"
                    )
            except BaseException:
                _terminate(process, self.config.runtime.shutdown_timeout_seconds)
                raise

    def run(self) -> None:
        segments = plan_segments(self.config)
        self.ledger.write_manifest("supervisor_running", segments=len(segments))
        for segment in segments:
            if _segment_complete(segment, self.config, self.ledger):
                continue
            last_error: Exception | None = None
            for attempt in range(1, self.config.runtime.max_worker_restarts + 2):
                try:
                    self._run_attempt(segment, attempt)
                    self.ledger = CommitLedger(
                        self.config.output,
                        run_id=self.config.run_id,
                        fingerprint=self.config.fingerprint,
                    )
                    if not _segment_complete(segment, self.config, self.ledger):
                        raise RuntimeError(
                            f"Worker exited successfully but segment is not fully committed: {segment.segment_id}"
                        )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    self.ledger.write_manifest(
                        "worker_restart",
                        segment_id=segment.segment_id,
                        attempt=attempt,
                        error=repr(exc),
                    )
                    if isinstance(exc, WorkerTerminationError):
                        raise
            if last_error is not None:
                self.ledger.write_manifest(
                    "failed", segment_id=segment.segment_id, error=repr(last_error)
                )
                raise last_error
        self.ledger.write_manifest("complete")
