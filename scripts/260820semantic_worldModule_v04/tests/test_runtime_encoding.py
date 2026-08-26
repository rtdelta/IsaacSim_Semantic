import unittest

import numpy as np

from semantic_world_v04.runtime.camera_driver import CameraRuntimeDriver
from semantic_world_v04.runtime.encoding import (
    SemanticPalette,
    encode_npy,
    encode_png,
)
from semantic_world_v04.core.models import SensorDefinition


class _Annotator:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def get_data(self):
        self.calls += 1
        return self.value


class RuntimeEncodingTests(unittest.TestCase):
    def test_palette_is_stable(self) -> None:
        first = SemanticPalette.color_for_id(17)
        second = SemanticPalette.color_for_id(17)
        self.assertEqual(first, second)
        self.assertEqual((0, 0, 0), SemanticPalette.color_for_id(0))

    def test_colorize_and_mapping(self) -> None:
        palette = SemanticPalette()
        changed = palette.update_from_info(
            {"idToLabels": {"1": {"class": "bucket"}, "2": "ground"}}
        )
        self.assertTrue(changed)
        ids = np.asarray([[0, 1], [2, 1]], dtype=np.uint32)
        color = palette.colorize(ids)
        self.assertEqual((2, 2, 3), color.shape)
        self.assertEqual([0, 0, 0], color[0, 0].tolist())
        self.assertEqual(
            list(SemanticPalette.color_for_id(1)), color[0, 1].tolist()
        )
        self.assertIn("1", palette.mapping_document()["ids"])

    def test_encoders_produce_expected_headers(self) -> None:
        ids = np.zeros((2, 2), dtype=np.uint32)
        self.assertTrue(encode_npy(ids).startswith(b"\x93NUMPY"))
        rgb = np.zeros((2, 2, 3), dtype=np.uint8)
        self.assertTrue(encode_png(rgb).startswith(b"\x89PNG"))

    def test_semantic_only_read_skips_rgb_annotator(self) -> None:
        sensor = SensorDefinition(
            sensor_id="camera",
            plugin="pinhole_camera",
            prim_path="/World/Camera",
        )
        driver = CameraRuntimeDriver(
            sensor,
            resolution=(64, 32),
            modalities=("rgb", "semantic_id", "semantic_color"),
        )
        driver.render_product = object()
        rgb = _Annotator(np.zeros((2, 2, 4), dtype=np.uint8))
        semantic = _Annotator(
            {"data": np.zeros((2, 2), dtype=np.uint32), "info": {}}
        )
        driver.annotators = {"rgb": rgb, "semantic": semantic}
        payload = driver.read(["semantic_id", "semantic_color"])
        self.assertNotIn("rgb", payload)
        self.assertEqual(0, rgb.calls)
        self.assertEqual(1, semantic.calls)


if __name__ == "__main__":
    unittest.main()

