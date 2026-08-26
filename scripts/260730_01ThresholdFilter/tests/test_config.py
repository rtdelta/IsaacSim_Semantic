from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from threshold_filter.config import load_config
from tests.helpers import create_dataset


class ConfigTests(unittest.TestCase):
    def test_loads_complete_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path, output_root, _ = create_dataset(Path(temporary))
            config = load_config(config_path)
            self.assertEqual(config.identity.mode, "legacy_zero_class_order")
            self.assertEqual(config.execution.workers, 2)
            self.assertEqual(config.output.root, output_root.resolve())
            self.assertEqual(
                config.rules.tooth_group.minimum_low_teeth,
                3,
            )

    def test_rejects_unknown_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path, _, _ = create_dataset(Path(temporary))
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw["unknown"] = True
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown fields"):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
