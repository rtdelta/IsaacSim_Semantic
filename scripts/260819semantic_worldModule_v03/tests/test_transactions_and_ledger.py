from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from semantic_world_v03.errors import ResumeError
from semantic_world_v03.ledger import CommitLedger, LedgerRecord
from semantic_world_v03.transactions import FrameTransaction


class TransactionAndLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_transaction_publishes_only_on_commit(self):
        transaction = FrameTransaction(self.root, "full", 0)
        staged = transaction.path("sensor/full/frame/data.bin")
        staged.write_bytes(b"ok")
        self.assertFalse((self.root / "sensor/full/frame/data.bin").exists())
        files = transaction.commit()
        self.assertEqual(files, ("sensor/full/frame/data.bin",))
        self.assertEqual((self.root / files[0]).read_bytes(), b"ok")

    def test_transaction_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with FrameTransaction(self.root, "full", 0) as transaction:
                transaction.path("sensor/data.bin").write_bytes(b"partial")
                raise RuntimeError("capture failed")
        self.assertFalse((self.root / "sensor/data.bin").exists())

    def test_ledger_resume_and_fingerprint_guard(self):
        ledger = CommitLedger(self.root, run_id="run", fingerprint="abc")
        ledger.record(
            LedgerRecord(
                "run", "abc", "full", 2, "capture", ("camera",), ("x",), time.time()
            )
        )
        resumed = CommitLedger(self.root, run_id="run", fingerprint="abc")
        self.assertTrue(resumed.contains("full", 2))
        with self.assertRaisesRegex(ResumeError, "fingerprint"):
            CommitLedger(self.root, run_id="run", fingerprint="different")


if __name__ == "__main__":
    unittest.main()

