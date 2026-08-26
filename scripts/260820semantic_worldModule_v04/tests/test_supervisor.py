import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler
from semantic_world_v04.core.errors import JobStateError
from semantic_world_v04.core.models import SensorDefinition
from semantic_world_v04.output import StatusStore
from semantic_world_v04.supervisor import GpuLock, SameHostSupervisor

from helpers import make_project


class SupervisorTests(unittest.TestCase):
    def test_submit_counts_each_enabled_sensor_variant_capture_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            project = make_project(str(output_root))
            project.sensors.append(
                SensorDefinition(
                    sensor_id="second_camera",
                    plugin="pinhole_camera",
                    prim_path="/World/SecondCamera",
                )
            )
            project.variants[0].modalities_by_sensor["second_camera"] = ["rgb"]
            job = JobCompiler().compile(project, job_id="job-multi-sensor")
            supervisor = SameHostSupervisor(
                runtime_command=[sys.executable],
                gpu_lock_path=Path(temp) / "gpu.lock",
            )

            status = supervisor.submit(job)

            # Two groups for boom_camera plus one full-scene group for the
            # second camera, multiplied by two frames.
            self.assertEqual(6, status.frame_total)

    def test_gpu_lock_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "gpu.lock"
            first = GpuLock(path)
            second = GpuLock(path)
            first.acquire()
            try:
                with self.assertRaises(OSError):
                    second.acquire()
            finally:
                first.release()
            second.acquire()
            second.release()

    def test_submit_and_short_process_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            project = make_project(str(output_root))
            job = JobCompiler().compile(
                project,
                source_project_path=str(Path(temp) / "demo.swproject"),
                job_id="job-short",
            )
            command = [
                sys.executable,
                "-c",
                (
                    "import argparse,time;"
                    "p=argparse.ArgumentParser();"
                    "p.add_argument('--job-spec');p.add_argument('--output-dir');"
                    "p.add_argument('--gpu-lock');a=p.parse_args();"
                    "time.sleep(0.2)"
                ),
            ]
            supervisor = SameHostSupervisor(
                runtime_command=command,
                gpu_lock_path=Path(temp) / "gpu.lock",
            )
            submitted = supervisor.submit(job)
            self.assertEqual("queued", submitted.state)
            started = supervisor.start(job.job_id, output_root)
            self.assertEqual("preflight", started.state)
            self.assertIsNotNone(started.process_token)
            deadline = time.monotonic() + 5
            status = started
            while time.monotonic() < deadline:
                status = supervisor.status(job.job_id, output_root)
                if status.state in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            self.assertEqual(
                "completed",
                status.state,
                msg=(
                    f"status={status}; logs="
                    f"{''.join(supervisor.tail_logs(job.job_id, output_root))}"
                ),
            )
            self.assertEqual(0, status.exit_code)

    def test_duplicate_submission_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            project = make_project(str(output_root))
            job = JobCompiler().compile(project, job_id="job-duplicate")
            supervisor = SameHostSupervisor(
                runtime_command=[sys.executable],
                gpu_lock_path=Path(temp) / "gpu.lock",
            )
            supervisor.submit(job)
            with self.assertRaises(JobStateError):
                supervisor.submit(job)

    def test_stale_process_identity_marks_job_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output_root = Path(temp) / "output"
            project = make_project(str(output_root))
            job = JobCompiler().compile(project, job_id="job-stale")
            supervisor = SameHostSupervisor(
                runtime_command=[sys.executable],
                gpu_lock_path=Path(temp) / "gpu.lock",
            )
            supervisor.submit(job)
            store = StatusStore(output_root / job.job_id / "status.json")
            status = store.read()
            status.state = "running"
            status.pid = 99999999
            status.process_token = "linux-start-ticks:invalid"
            store.write(status)
            refreshed = supervisor.status(job.job_id, output_root)
            self.assertEqual("failed", refreshed.state)


if __name__ == "__main__":
    unittest.main()
