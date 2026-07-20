"""Tests for authoritative capture frame context."""

from __future__ import annotations

import unittest

from capture_context import CaptureContext, CaptureLedger, CaptureReceipt, FrozenWorldSnapshot


class CaptureContextTests(unittest.TestCase):
    @staticmethod
    def context(frame_id: int) -> CaptureContext:
        return CaptureContext(
            frame_id=frame_id,
            dataset_time=frame_id / 10.0,
            timeline_time=frame_id / 10.0,
            physics_step=frame_id * 6,
            camera_path="/root/Camera",
            camera_world_transform=tuple(float(index) for index in range(16)),
            motion_state={},
        )

    def test_serializes_frame_context(self) -> None:
        context = CaptureContext(
            frame_id=2,
            dataset_time=0.2,
            timeline_time=0.3,
            physics_step=12,
            camera_path="/root/Camera",
            camera_world_transform=tuple(float(index) for index in range(16)),
            motion_state={"enabled": True, "targets": {"boom": 1.5}},
        )
        value = context.to_dict()
        self.assertEqual(value["frame_id"], 2)
        self.assertEqual(value["camera"]["path"], "/root/Camera")
        self.assertEqual(value["motion"]["targets"]["boom"], 1.5)

    def test_rejects_invalid_matrix(self) -> None:
        with self.assertRaisesRegex(ValueError, "16 values"):
            CaptureContext(
                frame_id=0,
                dataset_time=0.0,
                timeline_time=0.0,
                physics_step=0,
                camera_path="/root/Camera",
                camera_world_transform=(1.0,),
                motion_state={},
            )

    def test_snapshot_and_receipt_are_json_friendly(self) -> None:
        snapshot = FrozenWorldSnapshot(physics_step=6, dataset_time=0.1, timeline_time=0.1)
        receipt = CaptureReceipt(
            frame_id=1,
            rgb_path="rgb/rgb_0001.png",
            semantic_id_path="semantic_id/semantic_id_0001.npy",
            semantic_color_path="semantic_color/semantic_color_0001.png",
            runtime_id_path=None,
            metadata_path="metadata/frame_0001.json",
        )
        self.assertEqual(snapshot.to_dict()["physics_step"], 6)
        self.assertEqual(receipt.to_dict()["rgb"], "rgb/rgb_0001.png")

    def test_ledger_enforces_one_context_per_completion(self) -> None:
        ledger = CaptureLedger()
        context = self.context(0)
        ledger.arm(context)
        with self.assertRaisesRegex(RuntimeError, "more than once"):
            ledger.arm(context)
        self.assertEqual(ledger.consume(), context)
        receipt = CaptureReceipt(
            frame_id=0,
            rgb_path="rgb/rgb_0000.png",
            semantic_id_path="semantic_id/semantic_id_0000.npy",
            semantic_color_path="semantic_color/semantic_color_0000.png",
            runtime_id_path=None,
            metadata_path="metadata/frame_0000.json",
        )
        ledger.complete(receipt)
        self.assertEqual(ledger.require_completed(0), receipt)
        self.assertEqual(ledger.pending_count, 0)
        self.assertEqual(ledger.completed_count, 1)

    def test_ledger_rejects_callback_without_context(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "without an armed"):
            CaptureLedger().consume()


if __name__ == "__main__":
    unittest.main()
