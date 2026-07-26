import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from postprocess_chain.pipeline.orchestrator import Orchestrator
from postprocess_chain.pipeline.orchestrator_config import (
    load_orchestrator_config,
)


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.rgb_dir = self.root / "rgb"
        self.semantic_dir = self.root / "semantic"
        self.output_dir = self.root / "output"
        self.rgb_dir.mkdir()
        self.semantic_dir.mkdir()

        self.mapping_path = self.root / "semantic_mapping.json"
        self.mapping_path.write_text(
            json.dumps(
                {
                    "dataset_dtype": "uint16",
                    "classes": [
                        {"id": 1, "label": "tooth_1"},
                        {"id": 2, "label": "tooth_5"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        frame0 = np.zeros((4, 6), dtype=np.uint16)
        frame0[1:4, 0:2] = 1
        frame0[0:2, 4:6] = 2
        np.save(self.semantic_dir / "semantic_id_0000.npy", frame0)
        Image.new("RGB", (6, 4), "black").save(self.rgb_dir / "rgb_0000.png")

        frame1 = np.zeros((4, 6), dtype=np.uint16)
        frame1[1:4, 0:2] = 1
        np.save(self.semantic_dir / "semantic_id_0001.npy", frame1)
        Image.new("RGB", (6, 4), "black").save(self.rgb_dir / "rgb_0001.png")

        self.semantic_module_config = self.root / "semantic_module.json"
        self.semantic_module_config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "output": {
                        "directory": "modules/tooth_boxes",
                        "layout": "flat_yolo",
                    },
                    "min_pixels": 1,
                    "targets": [
                        {
                            "yolo_id": 0,
                            "yolo_name": "tooth",
                            "semantic_labels": ["tooth_1", "tooth_5"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        self.group_module_config = self.root / "group_module.json"
        self.group_module_config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_artifact": "tooth_boxes.semantic_boxes",
                    "output": {
                        "directory": "modules/tooth_group",
                        "layout": "flat_yolo",
                    },
                    "class": {
                        "yolo_id": 0,
                        "yolo_name": "tooth_group",
                    },
                    "endpoint_selector": {
                        "type": "semantic_labels",
                        "labels": ["tooth_1", "tooth_5"],
                    },
                    "min_pixels": 1,
                    "missing_policy": "exclude_frame",
                }
            ),
            encoding="utf-8",
        )

        self.orchestrator_config = self.root / "orchestrator.json"
        self.orchestrator_config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "inputs": {
                        "rgb_dir": str(self.rgb_dir),
                        "semantic_dir": str(self.semantic_dir),
                        "semantic_mapping": str(self.mapping_path),
                    },
                    "output_root": str(self.output_dir),
                    "execution": {
                        "workers": 1,
                        "max_in_flight": 1,
                        "overwrite": False,
                        "on_frame_error": "continue",
                    },
                    "output": {
                        "image_mode": "hardlink_or_copy",
                        "write_manifest": True,
                    },
                    "modules": [
                        {
                            "id": "tooth_boxes",
                            "type": "semantic_yolo_boxes",
                            "enabled": True,
                            "config": str(self.semantic_module_config),
                            "depends_on": [],
                        },
                        {
                            "id": "tooth_group",
                            "type": "tooth_group_yolo",
                            "enabled": True,
                            "config": str(self.group_module_config),
                            "depends_on": ["tooth_boxes"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_pipeline_writes_individual_and_group_datasets(self):
        config = load_orchestrator_config(self.orchestrator_config)
        return_code = Orchestrator(config).run()

        self.assertEqual(return_code, 0)
        individual_dir = self.output_dir / "modules" / "tooth_boxes"
        group_dir = self.output_dir / "modules" / "tooth_group"

        individual_lines = (
            individual_dir / "rgb_0000.txt"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(individual_lines), 2)
        self.assertEqual(
            (individual_dir / "classes.txt").read_text(encoding="utf-8"),
            "tooth\n",
        )
        self.assertTrue((individual_dir / "rgb_0001.txt").is_file())

        group_text = (group_dir / "rgb_0000.txt").read_text(encoding="utf-8")
        self.assertEqual(
            group_text,
            "0 0.50000000 0.50000000 1.00000000 1.00000000\n",
        )
        self.assertFalse((group_dir / "rgb_0001.txt").exists())
        self.assertFalse((group_dir / "rgb_0001.png").exists())
        self.assertEqual(
            (group_dir / "classes.txt").read_text(encoding="utf-8"),
            "tooth_group\n",
        )

        manifest = json.loads(
            (self.output_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "completed")
        summary = json.loads(
            (self.output_dir / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["modules"]["tooth_boxes"]["written"], 2)
        self.assertEqual(summary["modules"]["tooth_group"]["written"], 1)
        self.assertEqual(summary["modules"]["tooth_group"]["excluded"], 1)

    def test_resume_recomputes_artifact_but_skips_existing_outputs(self):
        config = load_orchestrator_config(self.orchestrator_config)
        self.assertEqual(Orchestrator(config).run(), 0)
        self.assertEqual(Orchestrator(config).run(), 0)

        summary = json.loads(
            (self.output_dir / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["modules"]["tooth_boxes"]["skipped"], 2)
        self.assertEqual(summary["modules"]["tooth_group"]["skipped"], 1)
        self.assertEqual(summary["modules"]["tooth_group"]["excluded"], 1)

    def test_pipeline_runs_with_multiple_workers(self):
        raw = json.loads(self.orchestrator_config.read_text(encoding="utf-8"))
        raw["execution"]["workers"] = 2
        raw["execution"]["max_in_flight"] = 2
        self.orchestrator_config.write_text(json.dumps(raw), encoding="utf-8")

        config = load_orchestrator_config(self.orchestrator_config)
        return_code = Orchestrator(config).run()

        self.assertEqual(return_code, 0)
        summary = json.loads(
            (self.output_dir / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["completed_frames"], 2)
        self.assertEqual(summary["failed_frames"], 0)

    def test_overwrite_removes_stale_output_for_excluded_frame(self):
        group_dir = self.output_dir / "modules" / "tooth_group"
        group_dir.mkdir(parents=True)
        (group_dir / "rgb_0001.txt").write_text("stale\n", encoding="utf-8")
        Image.new("RGB", (6, 4), "white").save(group_dir / "rgb_0001.png")

        raw = json.loads(self.orchestrator_config.read_text(encoding="utf-8"))
        raw["execution"]["overwrite"] = True
        self.orchestrator_config.write_text(json.dumps(raw), encoding="utf-8")

        config = load_orchestrator_config(self.orchestrator_config)
        self.assertEqual(Orchestrator(config).run(), 0)

        self.assertFalse((group_dir / "rgb_0001.txt").exists())
        self.assertFalse((group_dir / "rgb_0001.png").exists())

    def test_command_line_entry_uses_only_config_selector(self):
        project_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                str(project_root / "run_pipeline.py"),
                "--config",
                str(self.orchestrator_config),
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(
            (self.output_dir / "modules" / "tooth_group" / "rgb_0000.txt").is_file()
        )


if __name__ == "__main__":
    unittest.main()
