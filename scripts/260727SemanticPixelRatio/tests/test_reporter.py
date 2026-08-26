from __future__ import annotations

import unittest

import numpy as np

from semantic_pixel_ratio.config import TargetsConfig
from semantic_pixel_ratio.models import CountLedgerData
from semantic_pixel_ratio.results.reporter import build_rows, build_summary
from tests.helpers import LABELS


class ReporterTests(unittest.TestCase):
    def test_group_uses_summed_pixels_and_flags_edge_cases(self) -> None:
        ledger = CountLedgerData(
            ordinals=np.asarray([0, 1], dtype=np.int64),
            frame_ids=("0000", "0001"),
            whole_counts=np.asarray(
                [[1, 1, 0, 1, 1], [2, 0, 0, 0, 0]],
                dtype=np.uint32,
            ),
            reference_counts=np.asarray(
                [[2, 1, 1, 1, 1], [1, 0, 0, 0, 0]],
                dtype=np.uint32,
            ),
        )
        targets = TargetsConfig(
            labels=LABELS,
            group_name="tooth_front_group",
        )

        rows = build_rows(ledger, targets, pixels_per_frame=16)
        group_rows = [row for row in rows if row.target == "tooth_front_group"]

        self.assertAlmostEqual(group_rows[0].ratio, 4 / 6)
        self.assertEqual(group_rows[1].ratio, 2.0)
        self.assertEqual(group_rows[1].status, "ratio_over_one")
        tooth_2_second = [
            row
            for row in rows
            if row.frame_id == "0001" and row.target == LABELS[1]
        ][0]
        self.assertIsNone(tooth_2_second.ratio)
        self.assertEqual(tooth_2_second.status, "reference_missing")

        summary = build_summary(
            rows,
            (*LABELS, "tooth_front_group"),
            backend_name="numpy",
            elapsed_seconds=2.0,
        )
        group_summary = summary["targets"][-1]
        self.assertAlmostEqual(group_summary["aggregate_ratio"], 6 / 7)
        self.assertEqual(summary["frames"], 2)


if __name__ == "__main__":
    unittest.main()

