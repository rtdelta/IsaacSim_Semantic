"""Filesystem-backed same-host job supervisor."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from semantic_world_v04.compiler.job_compiler import JobCompiler, utc_now
from semantic_world_v04.core.errors import JobStateError
from semantic_world_v04.core.models import JobSpec, JobStatus
from semantic_world_v04.core.progress import capture_group_count
from semantic_world_v04.output.io import atomic_write_json, read_json
from semantic_world_v04.output.status_store import StatusStore

from .process_launcher import ProcessHandle, ProcessInspector, ProcessLauncher

TERMINAL_STATES = {"completed", "failed", "cancelled"}
ACTIVE_STATES = {"preflight", "running", "stopping"}


class SameHostSupervisor:
    """Submit immutable JobSpecs and launch v04 Runtime processes on this host."""

    def __init__(
        self,
        *,
        runtime_command: Optional[Sequence[str]] = None,
        launcher: Optional[ProcessLauncher] = None,
        gpu_lock_path: Optional[Path] = None,
        stop_timeout_seconds: float = 30.0,
    ) -> None:
        project_root = Path(__file__).resolve().parents[3]
        self.project_root = project_root
        self.runtime_command = list(
            runtime_command
            or [str(project_root / "scripts" / "launch_job_runner.sh")]
        )
        self.launcher = launcher or ProcessLauncher()
        self.gpu_lock_path = Path(
            gpu_lock_path
            or os.environ.get(
                "SEMANTIC_WORLD_GPU_LOCK",
                str(project_root / ".runtime" / "locks" / "gpu0.lock"),
            )
        )
        self._handles: Dict[str, ProcessHandle] = {}
        self.stop_timeout_seconds = float(stop_timeout_seconds)
        if self.stop_timeout_seconds < 0:
            raise ValueError("stop_timeout_seconds must not be negative")

    def submit(self, job_spec: JobSpec) -> JobStatus:
        if not JobCompiler.verify(job_spec):
            raise JobStateError("JobSpec content digest is invalid")
        job_dir = self.job_dir(job_spec)
        job_dir.mkdir(parents=True, exist_ok=True)
        spec_path = job_dir / "job_spec.json"
        status_store = StatusStore(job_dir / "status.json")
        if spec_path.exists() or status_store.exists():
            raise JobStateError(f"job already exists: {job_spec.job_id}")
        atomic_write_json(spec_path, job_spec.to_dict())
        now = utc_now()
        status = JobStatus(
            job_id=job_spec.job_id,
            state="queued",
            created_at_utc=now,
            updated_at_utc=now,
            frame_total=capture_group_count(job_spec.project),
            message="JobSpec submitted",
        )
        status_store.write(status)
        self._log_event(job_dir, status)
        return status

    def start(self, job_id: str, output_root: Path) -> JobStatus:
        job_dir = Path(output_root) / job_id
        store = StatusStore(job_dir / "status.json")
        status = store.read()
        if status.state not in {"queued", "failed", "cancelled"}:
            raise JobStateError(
                f"cannot start job {job_id} from state {status.state}"
            )
        spec_path = job_dir / "job_spec.json"
        job_spec = JobSpec.from_dict(read_json(spec_path))
        if not JobCompiler.verify(job_spec):
            raise JobStateError("persisted JobSpec content digest is invalid")

        logs_dir = job_dir / "logs"
        runtime_root = job_dir / ".runtime"
        environment = dict(os.environ)
        environment["SEMANTIC_WORLD_RUNTIME_ROOT"] = str(runtime_root)
        argv = [
            *self.runtime_command,
            "--job-spec",
            str(spec_path),
            "--output-dir",
            str(job_dir),
            "--gpu-lock",
            str(self.gpu_lock_path),
        ]
        handle = self.launcher.launch(
            argv,
            log_path=logs_dir / "job_runner.log",
            env=environment,
            cwd=self.project_root,
        )
        self._handles[job_id] = handle
        now = utc_now()
        status.state = "preflight"
        status.pid = handle.pid
        status.process_token = handle.token
        status.started_at_utc = now
        status.updated_at_utc = now
        status.completed_at_utc = None
        status.exit_code = None
        status.message = "Segmented Job Runner launched"
        store.write(status)
        self._log_event(job_dir, status)
        return status

    def status(self, job_id: str, output_root: Path) -> JobStatus:
        job_dir = Path(output_root) / job_id
        store = StatusStore(job_dir / "status.json")
        status = store.read()
        handle = self._handles.get(job_id)
        if handle is not None:
            exit_code = handle.process.poll()
            if exit_code is not None:
                handle.log_stream.close()
                self._handles.pop(job_id, None)
                refreshed = store.read()
                if refreshed.state not in TERMINAL_STATES:
                    refreshed.state = "completed" if exit_code == 0 else "failed"
                    refreshed.exit_code = exit_code
                    refreshed.completed_at_utc = utc_now()
                    refreshed.updated_at_utc = refreshed.completed_at_utc
                    refreshed.message = "Runtime exited without a terminal status update"
                    store.write(refreshed)
                return store.read()
            if status.state == "stopping" and self._stop_timed_out(status):
                return self._force_stop(status, Path(output_root), handle)
            # The Popen handle is authoritative while this supervisor process
            # owns it. Avoid a short-process race between poll() and a second
            # PID lookup in ProcessInspector.
            return status
        alive = ProcessInspector.matches(status.pid, status.process_token)
        if status.state == "stopping" and alive and self._stop_timed_out(status):
            return self._force_stop(status, Path(output_root), None)
        if status.state in ACTIVE_STATES and not alive:
            status.state = "failed"
            status.completed_at_utc = utc_now()
            status.updated_at_utc = status.completed_at_utc
            status.message = "Runtime process is no longer alive"
            store.write(status)
            self._log_event(job_dir, status)
        return status

    def _stop_timed_out(self, status: JobStatus) -> bool:
        if status.state != "stopping":
            return False
        try:
            updated = datetime.fromisoformat(
                status.updated_at_utc.replace("Z", "+00:00")
            )
        except ValueError:
            return True
        return (
            datetime.now(timezone.utc) - updated
        ).total_seconds() >= self.stop_timeout_seconds

    def _force_stop(
        self,
        status: JobStatus,
        output_root: Path,
        handle: Optional[ProcessHandle],
    ) -> JobStatus:
        if status.pid is None or status.process_token is None:
            raise JobStateError("stopping job has no valid process identity")
        if not self.launcher.kill(status.pid, status.process_token):
            raise JobStateError("runtime process identity changed before forced stop")
        self._kill_active_segment(Path(output_root) / status.job_id)
        exit_code = None
        if handle is not None:
            try:
                exit_code = handle.process.wait(timeout=5)
            except Exception:
                exit_code = None
            handle.log_stream.close()
            self._handles.pop(status.job_id, None)
        now = utc_now()
        status.state = "cancelled"
        status.exit_code = exit_code
        status.completed_at_utc = now
        status.updated_at_utc = now
        status.message = (
            f"Runtime force-terminated after {self.stop_timeout_seconds:g}s "
            "graceful-stop timeout"
        )
        StatusStore(output_root / status.job_id / "status.json").write(status)
        self._log_event(output_root / status.job_id, status)
        return status

    def stop(self, job_id: str, output_root: Path) -> JobStatus:
        status = self.status(job_id, output_root)
        if status.state not in ACTIVE_STATES:
            raise JobStateError(f"job {job_id} is not running")
        if status.pid is None or status.process_token is None:
            raise JobStateError("active job has no valid process identity")
        if not self.launcher.terminate(status.pid, status.process_token):
            raise JobStateError("runtime process identity changed before stop")
        status.state = "stopping"
        status.updated_at_utc = utc_now()
        status.message = "Graceful stop requested"
        StatusStore(Path(output_root) / job_id / "status.json").write(status)
        self._log_event(Path(output_root) / job_id, status)
        return status

    def resume(self, job_id: str, output_root: Path) -> JobStatus:
        status = self.status(job_id, output_root)
        if status.state not in {"failed", "cancelled"}:
            raise JobStateError(
                f"cannot resume job {job_id} from state {status.state}"
            )
        status.state = "queued"
        status.pid = None
        status.process_token = None
        status.exit_code = None
        status.completed_at_utc = None
        status.updated_at_utc = utc_now()
        status.message = "Resume queued"
        StatusStore(Path(output_root) / job_id / "status.json").write(status)
        self._log_event(Path(output_root) / job_id, status)
        return self.start(job_id, output_root)

    @staticmethod
    def tail_logs(job_id: str, output_root: Path, lines: int = 100) -> List[str]:
        if lines <= 0:
            return []
        root = Path(output_root) / job_id
        path = root / "logs" / "job_runner.log"
        if not path.exists():
            path = root / "logs" / "runtime.log"
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return stream.readlines()[-lines:]

    @staticmethod
    def job_dir(job_spec: JobSpec) -> Path:
        output_root = Path(job_spec.project.output.root_dir)
        if not output_root.is_absolute() and job_spec.source_project_path:
            output_root = Path(job_spec.source_project_path) / output_root
        return output_root / job_spec.job_id

    def _kill_active_segment(self, job_dir: Path) -> None:
        segments_dir = Path(job_dir) / "segments"
        if not segments_dir.is_dir():
            return
        for status_path in segments_dir.glob("*/status.json"):
            try:
                from semantic_world_v04.output import SegmentStatusStore

                segment = SegmentStatusStore(status_path).read()
                if (
                    segment.state in {"starting", "running", "stopping"}
                    and segment.pid is not None
                    and segment.process_token is not None
                ):
                    self.launcher.kill(segment.pid, segment.process_token)
            except Exception:
                continue

    @staticmethod
    def _log_event(job_dir: Path, status: JobStatus) -> None:
        path = Path(job_dir) / "logs" / "supervisor.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "at_utc": utc_now(),
            "job_id": status.job_id,
            "state": status.state,
            "pid": status.pid,
            "message": status.message,
        }
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
