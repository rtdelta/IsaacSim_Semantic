from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from postprocess_chain_v02.config import load_config
from postprocess_chain_v02.preflight import run_preflight

from tests.helpers import config_value, make_dataset, write_config


class ConfigTests(unittest.TestCase):
    def test_valid_config_uses_explicit_five_tooth_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            path = write_config(root / "config.json", config_value(root, inputs))
            config = load_config(path)
            self.assertEqual(
                [item.class_id for item in config.targets.teeth], list(range(5))
            )
            self.assertEqual(len(config.targets.teeth), 5)
            self.assertEqual(config.modules.visibility_ratio.zero_reference_value, -1)
            self.assertEqual(
                config.modules.threshold_rules.single_tooth.height_width_axis_mode,
                "x_over_y",
            )
            self.assertEqual(config.inputs.reference.capture_variant, "front_teeth_only")
            self.assertEqual(config.modules.component_filter.connectivity, 4)
            self.assertEqual(
                config.modules.component_filter.minimum_connected_component_pixels,
                5,
            )

    def test_non_four_neighborhood_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            raw = config_value(root, inputs)
            raw["modules"]["component_filter"]["connectivity"] = 8
            path = write_config(root / "config.json", raw)
            with self.assertRaisesRegex(ValueError, "connectivity must be 4"):
                load_config(path)

    def test_invalid_height_width_axis_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            raw = config_value(root, inputs)
            raw["modules"]["threshold_rules"]["single_tooth"][
                "height_width_axis_mode"
            ] = "z_over_x"
            path = write_config(root / "config.json", raw)
            with self.assertRaisesRegex(ValueError, "height_width_axis_mode"):
                load_config(path)

    def test_unknown_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            raw = config_value(root, inputs)
            raw["pipeline"]["unexpected"] = True
            path = write_config(root / "config.json", raw)
            with self.assertRaisesRegex(ValueError, "unknown fields"):
                load_config(path)

    def test_target_id_must_fit_semantic_dtype(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = make_dataset(root)
            mapping = json.loads(inputs["mapping"].read_text(encoding="utf-8"))
            mapping["classes"][0]["id"] = 70000
            inputs["mapping"].write_text(json.dumps(mapping), encoding="utf-8")
            path = write_config(root / "config.json", config_value(root, inputs))
            with self.assertRaisesRegex(ValueError, "cannot be represented"):
                run_preflight(load_config(path))


if __name__ == "__main__":
    unittest.main()
