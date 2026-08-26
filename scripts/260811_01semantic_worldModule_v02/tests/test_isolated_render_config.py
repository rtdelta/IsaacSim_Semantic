"""Tests for the external isolated-render Prim whitelist."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from isolated_render_config import IsolatedRenderConfig


class IsolatedRenderConfigTests(unittest.TestCase):
    @staticmethod
    def write_config(directory: Path, payload: Any) -> Path:
        path = directory / "isolated.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_absolute_non_overlapping_prim_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                {
                    "schema_version": 1,
                    "render_prim_paths": ["/root/Xform", "/root/Light"],
                },
            )
            config = IsolatedRenderConfig.load(path)
            self.assertEqual(config.render_prim_paths, ("/root/Xform", "/root/Light"))
            self.assertEqual(config.source_path, path.resolve())

    def test_rejects_relative_prim_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                {"schema_version": 1, "render_prim_paths": ["root/Xform"]},
            )
            with self.assertRaisesRegex(ValueError, "absolute USD Prim path"):
                IsolatedRenderConfig.load(path)

    def test_rejects_redundant_descendant_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                {
                    "schema_version": 1,
                    "render_prim_paths": [
                        "/root/Xform",
                        "/root/Xform/operator_cab_mesh",
                    ],
                },
            )
            with self.assertRaisesRegex(ValueError, "redundant descendant"):
                IsolatedRenderConfig.load(path)

    def test_project_sample_is_loadable(self) -> None:
        sample = (
            Path(__file__).resolve().parents[1]
            / "configs"
            / "excavator_only_render_prims.json"
        )
        config = IsolatedRenderConfig.load(sample)
        self.assertIn("/root/Xform", config.render_prim_paths)


if __name__ == "__main__":
    unittest.main()
