import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from postprocess_chain.common.models import FrameTask, SemanticBoxSet
from postprocess_chain.modules.semantic_yolo_boxes.module import (
    SemanticYoloBoxesModule,
)
from postprocess_chain.pipeline.frame_context import (
    FrameArtifactStore,
    FrameContext,
)
from postprocess_chain.pipeline.module_base import RunContext
from postprocess_chain.pipeline.orchestrator_config import ModuleSpec


class SemanticYoloBoxesModuleTests(unittest.TestCase):
    def test_keeps_small_box_in_artifact_but_not_yolo_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "module.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "output": {
                            "directory": "semantic",
                            "layout": "flat_yolo",
                        },
                        "min_pixels": 2,
                        "targets": [
                            {
                                "yolo_id": 0,
                                "yolo_name": "tooth",
                                "semantic_labels": ["tooth_1", "tooth_2"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            run_context = RunContext(
                output_root=root / "output",
                label_to_id={"tooth_1": 1, "tooth_2": 2},
                expected_dtype="uint16",
                overwrite=False,
                image_mode="none",
            )
            spec = ModuleSpec(
                module_id="semantic",
                module_type="semantic_yolo_boxes",
                enabled=True,
                config_path=config_path,
                depends_on=(),
            )
            module = SemanticYoloBoxesModule.from_config(spec, run_context)
            semantic = np.zeros((3, 4), dtype=np.uint16)
            semantic[0, 0:2] = 1
            semantic[2, 3] = 2
            frame = FrameContext(
                task=FrameTask("0000", root / "rgb.png", root / "semantic.npy"),
                semantic=semantic,
                image_width=4,
                image_height=3,
            )

            result = module.process_frame(frame, FrameArtifactStore())

            artifact = result.artifacts["semantic_boxes"]
            self.assertIsInstance(artifact, SemanticBoxSet)
            self.assertEqual(len(artifact.boxes), 2)
            self.assertEqual(len(result.annotation.detections), 1)
            self.assertEqual(result.metrics["small_masks"], 1)


if __name__ == "__main__":
    unittest.main()
