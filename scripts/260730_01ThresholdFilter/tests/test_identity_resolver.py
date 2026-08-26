from __future__ import annotations

import unittest

import numpy as np

from threshold_filter.identity_resolver import (
    ClassIdMapResolver,
    LegacyZeroClassOrderResolver,
)
from threshold_filter.models import YoloAnnotation
from tests.helpers import LABELS


def annotation(class_id: int, line_number: int) -> YoloAnnotation:
    return YoloAnnotation(
        class_id=class_id,
        x_center=0.5,
        y_center=0.5,
        width=0.1,
        height=0.1,
        raw_line=f"{class_id} 0.5 0.5 0.1 0.1",
        line_number=line_number,
    )


class IdentityResolverTests(unittest.TestCase):
    def test_legacy_order_skips_missing_middle_tooth(self) -> None:
        resolver = LegacyZeroClassOrderResolver(LABELS, source_class_id=0)
        resolved = resolver.resolve(
            [annotation(0, index) for index in range(1, 5)],
            np.asarray([True, False, True, True, True]),
        )
        self.assertEqual(
            [item.semantic_label for item in resolved],
            [LABELS[0], LABELS[2], LABELS[3], LABELS[4]],
        )

    def test_legacy_order_rejects_count_mismatch(self) -> None:
        resolver = LegacyZeroClassOrderResolver(LABELS, source_class_id=0)
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            resolver.resolve(
                [annotation(0, 1)],
                np.asarray([True, True, False, False, False]),
            )

    def test_class_map_supports_ids_one_through_five_and_source_order(self) -> None:
        mapping = {index + 1: label for index, label in enumerate(LABELS)}
        resolver = ClassIdMapResolver(LABELS, mapping)
        resolved = resolver.resolve(
            [annotation(5, 1), annotation(1, 2), annotation(3, 3)],
            np.zeros(5, dtype=np.bool_),
        )
        self.assertEqual(
            [item.semantic_label for item in resolved],
            [LABELS[4], LABELS[0], LABELS[2]],
        )


if __name__ == "__main__":
    unittest.main()
