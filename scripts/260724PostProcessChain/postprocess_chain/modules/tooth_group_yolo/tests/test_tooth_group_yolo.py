import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from postprocess_chain.common.models import (
    FrameTask,
    PixelBox,
    SemanticBox,
    SemanticBoxSet,
)
from postprocess_chain.modules.tooth_group_yolo.module import ToothGroupYoloModule
from postprocess_chain.pipeline.frame_context import (
    FrameArtifactStore,
    FrameContext,
)
from postprocess_chain.pipeline.module_base import RunContext
from postprocess_chain.pipeline.orchestrator_config import ModuleSpec


class ToothGroupYoloModuleTests(unittest.TestCase):
    def _make_module(self, root: Path) -> ToothGroupYoloModule:
        config_path = root / "group.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_artifact": "source.semantic_boxes",
                    "output": {
                        "directory": "group",
                        "layout": "flat_yolo",
                    },
                    "class": {"yolo_id": 0, "yolo_name": "tooth_group"},
                    "endpoint_selector": {
                        "type": "semantic_labels",
                        "labels": ["tooth_1", "tooth_5"],
                    },
                    "min_pixels": 2,
                    "missing_policy": "exclude_frame",
                }
            ),
            encoding="utf-8",
        )
        run_context = RunContext(
            output_root=root / "output",
            label_to_id={},
            expected_dtype="uint16",
            overwrite=False,
            image_mode="none",
        )
        spec = ModuleSpec(
            module_id="group",
            module_type="tooth_group_yolo",
            enabled=True,
            config_path=config_path,
            depends_on=("source",),
        )
        module = ToothGroupYoloModule.from_config(spec, run_context)
        module.validate(run_context)
        return module

    def test_generates_group_box_from_endpoint_edges(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._make_module(root)
            artifacts = FrameArtifactStore()
            artifacts.publish(
                "source",
                {
                    "semantic_boxes": SemanticBoxSet(
                        (
                            SemanticBox(
                                "tooth_1",
                                1,
                                20,
                                PixelBox(10, 20, 15, 40),
                            ),
                            SemanticBox(
                                "tooth_5",
                                5,
                                20,
                                PixelBox(30, 12, 39, 35),
                            ),
                        )
                    )
                },
            )
            frame = FrameContext(
                FrameTask("0000", root / "rgb.png", root / "semantic.npy"),
                np.zeros((50, 50), dtype=np.uint16),
                50,
                50,
            )

            result = module.process_frame(frame, artifacts)

            self.assertEqual(
                result.annotation.detections[0].box,
                PixelBox(10, 12, 39, 40),
            )
            self.assertEqual(result.artifacts["group_box"], PixelBox(10, 12, 39, 40))

    def test_excludes_frame_when_endpoint_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._make_module(root)
            artifacts = FrameArtifactStore()
            artifacts.publish(
                "source",
                {
                    "semantic_boxes": SemanticBoxSet(
                        (
                            SemanticBox(
                                "tooth_1",
                                1,
                                20,
                                PixelBox(10, 20, 15, 40),
                            ),
                        )
                    )
                },
            )
            frame = FrameContext(
                FrameTask("0000", root / "rgb.png", root / "semantic.npy"),
                np.zeros((50, 50), dtype=np.uint16),
                50,
                50,
            )

            result = module.process_frame(frame, artifacts)

            self.assertEqual(result.disposition, "exclude")
            self.assertIsNone(result.annotation)


if __name__ == "__main__":
    unittest.main()
