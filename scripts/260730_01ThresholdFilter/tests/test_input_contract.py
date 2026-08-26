from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from threshold_filter.config import load_config
from threshold_filter.file_index import build_file_index
from threshold_filter.preflight import run_preflight
from threshold_filter.ratio_reader import load_ratio_matrix
from tests.helpers import create_dataset


class InputContractTests(unittest.TestCase):
    def test_preflight_rejects_mismatched_semantic_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, ratio_root = create_dataset(root)
            manifest_path = ratio_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["inputs"]["whole_scene_semantic_dir"] = "/another/dataset"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                run_preflight(load_config(config_path))

    def test_file_index_allows_group_subset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path, _, _ = create_dataset(root)
            group_dir = root / "post" / "modules" / "tooth_group"
            (group_dir / "rgb_0002.txt").unlink()
            (group_dir / "rgb_0002.png").unlink()
            config = load_config(config_path)
            contract = run_preflight(config)
            ratios = load_ratio_matrix(config, contract)
            file_index = build_file_index(config, ratios)
            self.assertNotIn("0002", file_index.group.labels)
            self.assertEqual(len(file_index.tooth.labels), 3)


if __name__ == "__main__":
    unittest.main()
