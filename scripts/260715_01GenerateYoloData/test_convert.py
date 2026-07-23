import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import convert


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.rgb_dir = self.root / "rgb"
        self.semantic_dir = self.root / "semantic_id"
        self.output_dir = self.root / "output"
        self.rgb_dir.mkdir()
        self.semantic_dir.mkdir()
        self.output_dir.mkdir()

        self.mapping_path = self.root / "semantic_mapping.json"
        self.mapping_path.write_text(
            json.dumps(
                {
                    "dataset_dtype": "uint16",
                    "classes": [
                        {"id": 1, "label": "tooth_1"},
                        {"id": 2, "label": "tooth_2"},
                        {"id": 3, "label": "arm"},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_config(self, targets):
        config_path = self.root / "yolo_classes.json"
        config_path.write_text(
            json.dumps({"schema_version": 1, "targets": targets}),
            encoding="utf-8",
        )
        return config_path

    def test_split_directories_and_dynamic_classes(self):
        semantic = np.zeros((4, 6), dtype=np.uint16)
        semantic[1:3, 2:5] = 1
        semantic[0, 0] = 2
        semantic[3, 5] = 3
        np.save(self.semantic_dir / "semantic_id_0000.npy", semantic)
        Image.new("RGB", (6, 4), color="black").save(self.rgb_dir / "rgb_0000.png")

        config_path = self.write_config(
            [
                {
                    "yolo_id": 0,
                    "yolo_name": "tooth",
                    "semantic_labels": ["tooth_1", "tooth_2"],
                },
                {
                    "yolo_id": 1,
                    "yolo_name": "arm",
                    "semantic_labels": ["arm"],
                },
            ]
        )

        label_to_id, expected_dtype = convert.load_mapping(self.mapping_path)
        targets = convert.load_class_config(config_path, label_to_id)
        tasks = convert.discover_frame_tasks(self.rgb_dir, self.semantic_dir, self.output_dir)
        convert.init_worker(targets, min_pixels=1, overwrite=False, expected_dtype=expected_dtype)
        result = convert.process_frame(tasks[0])

        self.assertEqual(result["status"], "success")
        lines = (self.output_dir / "rgb_0000.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual([line.split()[0] for line in lines], ["0", "0", "1"])
        self.assertTrue((self.output_dir / "rgb_0000.png").is_file())

    def test_missing_mapping_label_is_rejected(self):
        config_path = self.write_config(
            [
                {
                    "yolo_id": 0,
                    "yolo_name": "missing",
                    "semantic_labels": ["not_in_mapping"],
                }
            ]
        )
        label_to_id, _ = convert.load_mapping(self.mapping_path)
        with self.assertRaisesRegex(ValueError, "不在 mapping 中"):
            convert.load_class_config(config_path, label_to_id)

    def test_cli_end_to_end(self):
        semantic = np.zeros((4, 6), dtype=np.uint16)
        semantic[1:3, 2:5] = 1
        np.save(self.semantic_dir / "semantic_id_0000.npy", semantic)
        Image.new("RGB", (6, 4), color="black").save(self.rgb_dir / "rgb_0000.png")
        config_path = self.write_config(
            [
                {
                    "yolo_id": 0,
                    "yolo_name": "configured_target",
                    "semantic_labels": ["tooth_1"],
                }
            ]
        )

        command = [
            sys.executable,
            str(Path(convert.__file__).resolve()),
            "--rgb-dir",
            str(self.rgb_dir),
            "--semantic-dir",
            str(self.semantic_dir),
            "--mapping",
            str(self.mapping_path),
            "--class-config",
            str(config_path),
            "--output",
            str(self.output_dir),
            "--workers",
            "1",
            "--max-in-flight",
            "1",
            "--min-pixels",
            "1",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            (self.output_dir / "classes.txt").read_text(encoding="utf-8"),
            "configured_target\n",
        )
        label = (self.output_dir / "rgb_0000.txt").read_text(encoding="utf-8")
        self.assertTrue(label.startswith("0 "))

    def test_yolo_ids_must_be_contiguous(self):
        config_path = self.write_config(
            [
                {
                    "yolo_id": 1,
                    "yolo_name": "tooth",
                    "semantic_labels": ["tooth_1"],
                }
            ]
        )
        label_to_id, _ = convert.load_mapping(self.mapping_path)
        with self.assertRaisesRegex(ValueError, "连续编号"):
            convert.load_class_config(config_path, label_to_id)

    def test_unpaired_frames_are_rejected_before_processing(self):
        semantic = np.zeros((4, 6), dtype=np.uint16)
        np.save(self.semantic_dir / "semantic_id_0000.npy", semantic)
        with self.assertRaisesRegex(ValueError, "缺少 RGB"):
            convert.discover_frame_tasks(self.rgb_dir, self.semantic_dir, self.output_dir)


if __name__ == "__main__":
    unittest.main()
