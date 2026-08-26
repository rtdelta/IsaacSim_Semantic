from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from formatter.config import load_config
from tests.helpers import make_source, write_config


class ConfigTests(unittest.TestCase):
    def test_loads_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0"])
            path = write_config(
                root / "config.json",
                input_root=source,
                output_root=root / "Formatted",
            )
            config = load_config(path)
            self.assertEqual(config.filename_prefix, "Sim_Fangshan_tooth_260813")
            self.assertEqual(config.performance.workers, 4)

    def test_unknown_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0"])
            path = write_config(
                root / "config.json",
                input_root=source,
                output_root=root / "Formatted",
                overrides={"unexpected": True},
            )
            with self.assertRaisesRegex(ValueError, "unknown fields"):
                load_config(path)

    def test_nested_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0"])
            path = write_config(
                root / "config.json",
                input_root=source,
                output_root=source / "Formatted",
            )
            with self.assertRaisesRegex(ValueError, "non-nested"):
                load_config(path)

    def test_trailing_underscore_prefix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ["0"])
            path = write_config(
                root / "config.json",
                input_root=source,
                output_root=root / "Formatted",
                prefix="bad_",
            )
            with self.assertRaisesRegex(ValueError, "must not end"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
