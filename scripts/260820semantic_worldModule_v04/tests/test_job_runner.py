import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from semantic_world_v04.compiler import JobCompiler
from semantic_world_v04.core.models import JobStatus
from semantic_world_v04.output import FrameLedger, StatusStore
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.supervisor.job_runner import JobRunner

from helpers import make_project


class FakeTelemetry:
    def __init__(self) -> None:
        self.gpu_events = []
        self.progress_events = []
        self.timing_events = []

    def sample_gpu(self, *, segment_id, worker_pid):
        event = {
            "available": True,
            "devices": [{"memory_used_mb": 123}],
            "segment_id": segment_id,
            "worker_pid": worker_pid,
        }
        self.gpu_events.append(event)
        return event

    def progress(self, value):
        self.progress_events.append(value)

    def segment_timing(self, value):
        self.timing_events.append(value)


class JobRunnerTests(unittest.TestCase):
    def _fixture(self, temp: str, *, frame_count: int = 5, segment_frames: int = 2):
        root = Path(temp)
        output = root / "output" / "job-segmented"
        project = make_project(str(root / "output"))
        project.capture.frame_count = frame_count
        project.capture.segment_frames = segment_frames
        project.execution.telemetry_interval_seconds = 0.02
        job = JobCompiler().compile(project, job_id="job-segmented")
        spec_path = output / "job_spec.json"
        atomic_write_json(spec_path, job.to_dict())
        now = "2026-08-25T00:00:00Z"
        StatusStore(output / "status.json").write(
            JobStatus(
                job_id=job.job_id,
                state="preflight",
                created_at_utc=now,
                updated_at_utc=now,
                frame_total=frame_count * 2,
            )
        )
        worker = Path(__file__).with_name("fake_segment_worker.py")
        return output, spec_path, [sys.executable, str(worker)]

    def test_job_runner_executes_segments_and_resume_skips_committed_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output, spec_path, command = self._fixture(temp)
            telemetry = FakeTelemetry()
            runner = JobRunner(
                job_spec_path=spec_path,
                output_dir=output,
                gpu_lock_path=Path(temp) / "gpu.lock",
                worker_command=command,
                cancelled=lambda: False,
                telemetry=telemetry,
                poll_interval_seconds=0.01,
            )
            self.assertEqual(0, runner.run())
            status = StatusStore(output / "status.json").read()
            self.assertEqual("completed", status.state)
            self.assertEqual(10, status.frame_current)
            self.assertEqual(3, status.segment_total)
            self.assertEqual(10, len(list(FrameLedger(output / "ledger.jsonl").entries())))
            markers = sorted((output / "segments").glob("*/fake_worker.marker"))
            self.assertEqual(3, len(markers))
            before = [path.stat().st_mtime_ns for path in markers]

            second = JobRunner(
                job_spec_path=spec_path,
                output_dir=output,
                gpu_lock_path=Path(temp) / "gpu.lock",
                worker_command=command,
                cancelled=lambda: False,
                telemetry=FakeTelemetry(),
                poll_interval_seconds=0.01,
            )
            self.assertEqual(0, second.run())
            self.assertEqual(before, [path.stat().st_mtime_ns for path in markers])

    def test_failed_worker_generates_failure_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output, spec_path, command = self._fixture(
                temp, frame_count=1, segment_frames=1
            )
            runner = JobRunner(
                job_spec_path=spec_path,
                output_dir=output,
                gpu_lock_path=Path(temp) / "gpu.lock",
                worker_command=command,
                cancelled=lambda: False,
                telemetry=FakeTelemetry(),
                poll_interval_seconds=0.01,
            )
            with mock.patch.dict(os.environ, {"V04_FAKE_WORKER_MODE": "fail"}):
                self.assertEqual(1, runner.run())
            status = StatusStore(output / "status.json").read()
            self.assertEqual("failed", status.state)
            report_path = output / "failure_report.json"
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("job-segmented", report["job_id"])
            self.assertTrue(report["resume_allowed"])
            self.assertTrue(report["resume"]["require_same_job_digest"])
            self.assertIn("python_executable", report["job_runner_environment"])
            self.assertIn("render_profile", report)
            self.assertIn("last_ledger_entry", report)

    def test_failed_worker_state_normalizes_masked_zero_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output, spec_path, command = self._fixture(
                temp, frame_count=1, segment_frames=1
            )
            runner = JobRunner(
                job_spec_path=spec_path,
                output_dir=output,
                gpu_lock_path=Path(temp) / "gpu.lock",
                worker_command=command,
                cancelled=lambda: False,
                telemetry=FakeTelemetry(),
                poll_interval_seconds=0.01,
            )
            with mock.patch.dict(os.environ, {"V04_FAKE_WORKER_MODE": "fail_zero"}):
                self.assertEqual(1, runner.run())
            status = StatusStore(output / "status.json").read()
            self.assertEqual("failed", status.state)
            self.assertEqual(1, status.exit_code)
            segment_status = next((output / "segments").glob("*/status.json"))
            self.assertEqual(
                1,
                json.loads(segment_status.read_text(encoding="utf-8"))["exit_code"],
            )

    def test_cancel_then_resume_preserves_committed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output, spec_path, command = self._fixture(
                temp, frame_count=8, segment_frames=8
            )
            cancel = threading.Event()
            runner = JobRunner(
                job_spec_path=spec_path,
                output_dir=output,
                gpu_lock_path=Path(temp) / "gpu.lock",
                worker_command=command,
                cancelled=cancel.is_set,
                telemetry=FakeTelemetry(),
                poll_interval_seconds=0.01,
            )
            result = []
            with mock.patch.dict(os.environ, {"V04_FAKE_WORKER_DELAY": "0.05"}):
                thread = threading.Thread(target=lambda: result.append(runner.run()))
                thread.start()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    entries = list(FrameLedger(output / "ledger.jsonl").entries())
                    if len(entries) >= 2:
                        break
                    time.sleep(0.02)
                cancel.set()
                thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            self.assertEqual([0], result)
            self.assertEqual("cancelled", StatusStore(output / "status.json").read().state)
            first_file = next((output / "fake").glob("*.bin"))
            before_bytes = first_file.read_bytes()
            before_mtime = first_file.stat().st_mtime_ns

            resumed = JobRunner(
                job_spec_path=spec_path,
                output_dir=output,
                gpu_lock_path=Path(temp) / "gpu.lock",
                worker_command=command,
                cancelled=lambda: False,
                telemetry=FakeTelemetry(),
                poll_interval_seconds=0.01,
            )
            self.assertEqual(0, resumed.run())
            self.assertEqual("completed", StatusStore(output / "status.json").read().state)
            self.assertEqual(before_bytes, first_file.read_bytes())
            self.assertEqual(before_mtime, first_file.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
