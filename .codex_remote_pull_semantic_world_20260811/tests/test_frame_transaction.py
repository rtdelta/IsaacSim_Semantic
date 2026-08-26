"""Tests for frame-level staged output publication."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from capture_context import CaptureReceipt, CaptureVariant
from frame_transaction import FrameStagingTransaction


def receipt(
    frame_id: int,
    variant: CaptureVariant,
    staged: str,
    final: str,
) -> CaptureReceipt:
    return CaptureReceipt(
        frame_id=frame_id,
        rgb_path=None,
        semantic_id_path=final,
        semantic_color_path=final + ".png",
        runtime_id_path=None,
        metadata_path=final + ".json",
        variant=variant,
        staged_files=((staged, final),),
    )


class FrameStagingTransactionTests(unittest.TestCase):
    def test_commit_publishes_all_files_and_removes_staging_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            transaction = FrameStagingTransaction(output)
            first_staged = transaction.staged_path(7, "full/a.npy")
            second_staged = transaction.staged_path(7, "front/b.npy")
            for relative, value in ((first_staged, b"a"), (second_staged, b"b")):
                path = output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)

            transaction.commit(
                7,
                (
                    receipt(7, CaptureVariant.FULL_SCENE, first_staged, "full/a.npy"),
                    receipt(
                        7,
                        CaptureVariant.FRONT_TEETH_ONLY,
                        second_staged,
                        "front/b.npy",
                    ),
                ),
            )

            self.assertEqual((output / "full/a.npy").read_bytes(), b"a")
            self.assertEqual((output / "front/b.npy").read_bytes(), b"b")
            self.assertFalse((output / transaction.staging_prefix(7)).exists())
            self.assertEqual(transaction.committed_frame_count, 1)

    def test_preflight_failure_does_not_publish_partial_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            transaction = FrameStagingTransaction(output)
            first_staged = transaction.staged_path(1, "full/a.npy")
            first_source = output / first_staged
            first_source.parent.mkdir(parents=True, exist_ok=True)
            first_source.write_bytes(b"a")
            missing_staged = transaction.staged_path(1, "front/missing.npy")

            with self.assertRaisesRegex(RuntimeError, "missing"):
                transaction.commit(
                    1,
                    (
                        receipt(
                            1,
                            CaptureVariant.FULL_SCENE,
                            first_staged,
                            "full/a.npy",
                        ),
                        receipt(
                            1,
                            CaptureVariant.FRONT_TEETH_ONLY,
                            missing_staged,
                            "front/missing.npy",
                        ),
                    ),
                )

            self.assertTrue(first_source.is_file())
            self.assertFalse((output / "full/a.npy").exists())

    def test_discard_removes_only_requested_frame_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            transaction = FrameStagingTransaction(output)
            frame_two = output / transaction.staged_path(2, "x/file.npy")
            frame_three = output / transaction.staged_path(3, "x/file.npy")
            for path in (frame_two, frame_three):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")

            transaction.discard(2)

            self.assertFalse(frame_two.exists())
            self.assertTrue(frame_three.exists())

    def test_commit_can_atomically_replace_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            transaction = FrameStagingTransaction(output, allow_overwrite=True)
            staged = transaction.staged_path(5, "full/a.npy")
            source = output / staged
            destination = output / "full/a.npy"
            source.parent.mkdir(parents=True, exist_ok=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"new")
            destination.write_bytes(b"old")

            transaction.commit(
                5,
                (receipt(5, CaptureVariant.FULL_SCENE, staged, "full/a.npy"),),
            )

            self.assertEqual(destination.read_bytes(), b"new")
            self.assertFalse((output / transaction.staging_prefix(5)).exists())

    def test_commit_requires_full_scene_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            transaction = FrameStagingTransaction(temporary)
            with self.assertRaisesRegex(RuntimeError, "without full_scene"):
                transaction.commit(
                    0,
                    (
                        receipt(
                            0,
                            CaptureVariant.FRONT_TEETH_ONLY,
                            ".frame_staging/frame_0000/front/a.npy",
                            "front/a.npy",
                        ),
                    ),
                )


if __name__ == "__main__":
    unittest.main()
