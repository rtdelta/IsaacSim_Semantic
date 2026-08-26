import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from semantic_world_v04.core.models import JobStatus
from semantic_world_v04.output import AtomicFrameWriter, FrameLedger, StatusStore
from semantic_world_v04.output.io import atomic_write_json, read_json


class OutputTests(unittest.TestCase):
    def test_atomic_json_retries_transient_windows_replace_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            import semantic_world_v04.output.io as io_module

            original_replace = io_module.os.replace
            calls = []

            def flaky_replace(source, destination):
                calls.append((source, destination))
                if len(calls) == 1:
                    raise PermissionError("transient sharing violation")
                return original_replace(source, destination)

            with mock.patch.object(io_module.os, "replace", side_effect=flaky_replace), mock.patch.object(
                io_module.time, "sleep"
            ):
                atomic_write_json(path, {"value": 1})
            self.assertEqual({"value": 1}, read_json(path))
            self.assertEqual(2, len(calls))

    def test_atomic_capture_group_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = FrameLedger(root / "ledger.jsonl")
            writer = AtomicFrameWriter(root, ledger)
            entry = writer.commit(
                frame_index=1,
                sensor_id="camera",
                variant_id="semantic_only",
                simulation_time=0.1,
                requested_modalities=["semantic_id", "semantic_color"],
                artifacts={
                    "sensors/camera/semantic_only/semantic_id/000001.npy": b"NPY",
                    "sensors/camera/semantic_only/semantic_color/000001.png": b"PNG",
                    "sensors/camera/semantic_only/metadata/000001.json": "{}\n",
                },
            )
            self.assertTrue(
                ledger.is_committed(1, "camera", "semantic_only")
            )
            self.assertNotIn("rgb", entry.files)
            self.assertFalse(
                (root / "sensors/camera/semantic_only/rgb/000001.png").exists()
            )
            self.assertTrue(
                (root / "sensors/camera/semantic_only/semantic_id/000001.npy").is_file()
            )

            # A retry returns the existing commit and does not replace outputs.
            retry = writer.commit(
                frame_index=1,
                sensor_id="camera",
                variant_id="semantic_only",
                simulation_time=999.0,
                requested_modalities=["rgb"],
                artifacts={"unexpected.txt": b"not-written"},
            )
            self.assertEqual(entry, retry)
            self.assertFalse((root / "unexpected.txt").exists())

            reloaded = FrameLedger(root / "ledger.jsonl")
            self.assertEqual(1, len(list(reloaded.entries())))

    def test_unsafe_artifact_path_is_rejected_without_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = FrameLedger(root / "ledger.jsonl")
            writer = AtomicFrameWriter(
                root, ledger, retain_staging_on_failure=False
            )
            with self.assertRaisesRegex(ValueError, "unsafe"):
                writer.commit(
                    frame_index=0,
                    sensor_id="camera",
                    variant_id="full",
                    simulation_time=0.0,
                    requested_modalities=["rgb"],
                    artifacts={"../escape.png": b"x"},
                )
            self.assertFalse(ledger.is_committed(0, "camera", "full"))
            self.assertFalse((root.parent / "escape.png").exists())

    def test_resume_rejects_ledger_entry_with_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = FrameLedger(root / "ledger.jsonl")
            writer = AtomicFrameWriter(root, ledger)
            writer.commit(
                frame_index=0,
                sensor_id="camera",
                variant_id="full",
                simulation_time=0.0,
                requested_modalities=["rgb"],
                artifacts={"sensors/camera/full/rgb/000000.png": b"PNG"},
            )
            (root / "sensors/camera/full/rgb/000000.png").unlink()

            with self.assertRaisesRegex(RuntimeError, "missing or empty"):
                writer.is_committed(0, "camera", "full")

    def test_status_store_is_strict_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = StatusStore(Path(temp) / "status.json")
            status = JobStatus(
                job_id="job-1",
                state="running",
                pid=123,
                frame_current=2,
                frame_total=10,
            )
            store.write(status)
            self.assertEqual(status, store.read())
            data = json.loads(store.path.read_text(encoding="utf-8"))
            data["typo"] = True
            store.path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(Exception):
                store.read()


if __name__ == "__main__":
    unittest.main()
