from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]
POSTPROCESS = PROJECT.parent / "260731PostProcessChain_v02"
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(POSTPROCESS))

from capture_postprocess_formatter import convert_dataset, load_config
from postprocess_chain_v02.common.semantic_mapping import load_semantic_mapping
from postprocess_chain_v02.frame_discovery import discover_frame_tasks


class ConversionTests(unittest.TestCase):
    def build_source(self, root: Path, *, omit_reference_last: bool = False) -> Path:
        source = root / "v03_boom_camera"
        variants = ("full_scene", "front_teeth_only", "excavator_only")
        for variant in variants:
            for frame_id in range(2):
                if omit_reference_last and variant == "front_teeth_only" and frame_id == 1:
                    continue
                frame = source / variant / f"frame_{frame_id:08d}"
                frame.mkdir(parents=True)
                semantic = np.zeros((6, 8), dtype=np.uint16)
                semantic[1:3, 2:4] = 5
                np.save(frame / "semantic_class_id.npy", semantic, allow_pickle=False)
                Image.fromarray(np.zeros((6, 8, 3), dtype=np.uint8)).save(
                    frame / "semantic_color.png"
                )
                if variant == "full_scene":
                    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(frame / "rgb.png")
                (frame / "packet.json").write_text(
                    json.dumps({"frame_id": frame_id, "variant_id": variant}),
                    encoding="utf-8",
                )
        return source

    def write_mapping(self, root: Path) -> Path:
        path = root / "mapping.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "classes": [
                        {"id": 0, "name": "BACKGROUND", "color": [0, 0, 0]},
                        *[
                            {
                                "id": value,
                                "name": f"tooth_{index:02d}_front_3DGS",
                                "color": [value, value, value],
                            }
                            for index, value in enumerate((5, 7, 9, 11, 13), start=1)
                        ],
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def write_config(self, root: Path, source: Path, mapping: Path) -> Path:
        config = root / "config.json"
        config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_root": str(source),
                    "output_root": str(root / "converted"),
                    "semantic_mapping": str(mapping),
                    "contract": {
                        "full_scene_variant": "full_scene",
                        "reference_variant": "front_teeth_only",
                        "additional_variants": ["excavator_only"],
                        "strict_pairing": True,
                        "include_semantic_color": True,
                        "include_packet_metadata": True,
                    },
                    "materialization": {"mode": "hardlink", "workers": 4},
                    "validation": {"level": "full"},
                }
            ),
            encoding="utf-8",
        )
        return config

    def test_output_is_postprocess_v02_compatible_and_hardlinked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.build_source(root)
            config = load_config(self.write_config(root, source, self.write_mapping(root)))
            summary = convert_dataset(config)

            self.assertEqual(summary.frame_count, 2)
            self.assertEqual(summary.semantic_shape, (6, 8))
            self.assertEqual(summary.semantic_dtype, "uint16")
            self.assertEqual(summary.copy_count, 0)
            output = root / "converted"
            source_rgb = source / "full_scene/frame_00000000/rgb.png"
            converted_rgb = output / "full_scene_rgb/rgb_00000000.png"
            self.assertTrue(source_rgb.samefile(converted_rgb))
            self.assertTrue(
                (output / "teeth_only_semantic/semantic_id/semantic_id_00000001.npy").is_file()
            )
            self.assertTrue(
                (output / "excavator_only_semantic/semantic_color/semantic_color_00000001.png").is_file()
            )

            inputs = SimpleNamespace(
                full_scene=SimpleNamespace(
                    rgb_dir=output / "full_scene_rgb",
                    semantic_dir=output / "full_scene_semantic/semantic_id",
                ),
                reference=SimpleNamespace(
                    semantic_dir=output / "teeth_only_semantic/semantic_id"
                ),
            )
            tasks = discover_frame_tasks(SimpleNamespace(inputs=inputs))
            self.assertEqual(tuple(task.frame_id for task in tasks), ("00000000", "00000001"))

            mapping = load_semantic_mapping(output / "semantic_mapping.json")
            self.assertEqual(mapping.expected_dtype, "uint16")
            self.assertEqual(mapping.label_to_id["tooth_05_front_3DGS"], 13)

    def test_strict_pairing_fails_without_publishing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.build_source(root, omit_reference_last=True)
            config = load_config(self.write_config(root, source, self.write_mapping(root)))
            with self.assertRaisesRegex(ValueError, "strict v03 frame pairing failed"):
                convert_dataset(config)
            self.assertFalse((root / "converted").exists())

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.build_source(root)
            config = load_config(self.write_config(root, source, self.write_mapping(root)))
            (root / "converted").mkdir()
            with self.assertRaises(FileExistsError):
                convert_dataset(config)


if __name__ == "__main__":
    unittest.main()

