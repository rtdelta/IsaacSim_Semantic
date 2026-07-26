import unittest

from postprocess_chain.common.box_geometry import (
    envelope_from_endpoint_boxes,
    select_image_extrema,
)
from postprocess_chain.common.models import PixelBox, SemanticBox


class BoxGeometryTests(unittest.TestCase):
    def test_endpoint_envelope_uses_outer_horizontal_and_vertical_edges(self):
        first = PixelBox(left=10, top=20, right=15, bottom=40)
        second = PixelBox(left=30, top=12, right=39, bottom=35)

        result = envelope_from_endpoint_boxes(first, second)

        self.assertEqual(result, PixelBox(left=10, top=12, right=39, bottom=40))

    def test_image_extrema_uses_box_centers_not_semantic_order(self):
        right = SemanticBox(
            semantic_label="tooth_1",
            semantic_id=1,
            pixel_count=20,
            box=PixelBox(30, 10, 40, 20),
        )
        left = SemanticBox(
            semantic_label="tooth_5",
            semantic_id=5,
            pixel_count=20,
            box=PixelBox(2, 11, 8, 21),
        )

        selected_left, selected_right = select_image_extrema((right, left))

        self.assertEqual(selected_left.semantic_label, "tooth_5")
        self.assertEqual(selected_right.semantic_label, "tooth_1")


if __name__ == "__main__":
    unittest.main()
