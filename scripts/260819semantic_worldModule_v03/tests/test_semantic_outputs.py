from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from conftest import config_payload, write_config
from semantic_world_v03.config import load_run_config
from semantic_world_v03.models import AcquisitionKind, SensorPacket
from semantic_world_v03.semantic_mapping import SemanticClass, SemanticMapping
from semantic_world_v03.sinks import FilesystemSink
from semantic_world_v03.transactions import FrameTransaction


class SemanticOutputTests(unittest.TestCase):
    @staticmethod
    def mapping() -> SemanticMapping:
        return SemanticMapping(
            (
                SemanticClass(0, "BACKGROUND", (0, 0, 0)),
                SemanticClass(15, "track_3DGS", (39, 232, 216)),
            ),
            {"BACKGROUND": 0, "track_3DGS": 15},
        )

    def test_stable_ids_use_uint16_for_dataset_class_range(self):
        mapped = self.mapping().remap(
            np.asarray([[3, 8]], dtype=np.uint32),
            {
                "idToLabels": {
                    "3": {"class": "BACKGROUND"},
                    "8": {"class": "track_3dgs"},
                }
            },
        )
        self.assertEqual(mapped.dtype, np.dtype(np.uint16))
        np.testing.assert_array_equal(mapped, np.asarray([[0, 15]], dtype=np.uint16))

    def test_sink_writes_stable_id_and_color_without_redundant_raw_array(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = config_payload(root / "output")
            payload["sensors"][0]["modalities"] = ["semantic_segmentation"]
            spec = load_run_config(write_config(root, payload)).sensors[0]
            packet = SensorPacket(
                run_id="run",
                capture_id="capture",
                frame_id=0,
                sample_id=0,
                sensor_id=spec.sensor_id,
                sensor_type=spec.sensor_type,
                variant_id="full_scene",
                acquisition=AcquisitionKind.SNAPSHOT,
                timestamp=0.0,
                physics_step=0,
                world_state_hash="world",
                calibration_hash="camera",
                payloads={
                    "semantic_segmentation": {
                        "data": np.asarray([[8]], dtype=np.uint32),
                        "info": {"idToLabels": {"8": {"class": "track_3dgs"}}},
                    }
                },
            )
            transaction = FrameTransaction(root / "output", "full_scene", 0)
            FilesystemSink(self.mapping()).write(transaction, spec, packet)
            transaction.commit()
            frame = root / "output/sensors/front/full_scene/frame_00000000"
            self.assertFalse((frame / "semantic_segmentation.npy").exists())
            self.assertEqual(
                np.load(frame / "semantic_class_id.npy").item(),
                15,
            )
            self.assertTrue((frame / "semantic_color.png").is_file())


if __name__ == "__main__":
    unittest.main()
