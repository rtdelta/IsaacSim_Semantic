"""Tests for project-relative CLI path handling."""

from __future__ import annotations

import argparse
import unittest
from pathlib import Path

from render_profile import RenderProfile
from simulation_orchestrator import (
    DEFAULT_RENDER_PROFILES,
    PROJECT_DIR,
    choose_default_render_profile,
    parse_args,
    resolve_project_relative_paths,
    resolve_renderer_selection,
)


class OrchestratorPathTests(unittest.TestCase):
    def test_resolves_relative_paths_from_project_root(self) -> None:
        args = argparse.Namespace(
            usd="configs/stage.usda",
            mapping="configs/mapping.json",
            render_profile="configs/profile.json",
            trajectory="trajectories/path.csv",
            output="output/run",
        )
        resolve_project_relative_paths(args)
        self.assertEqual(Path(args.output), (PROJECT_DIR / "output" / "run").resolve())
        self.assertEqual(
            Path(args.render_profile), (PROJECT_DIR / "configs" / "profile.json").resolve()
        )

    def test_renderer_selects_its_default_profile(self) -> None:
        args, kit_args = parse_args(["--renderer", "PathTracing"])
        self.assertEqual(kit_args, [])
        choose_default_render_profile(args)
        self.assertEqual(Path(args.render_profile), DEFAULT_RENDER_PROFILES["PathTracing"])

    def test_default_renderer_is_realtime_pathtracing(self) -> None:
        args, _ = parse_args([])
        choose_default_render_profile(args)
        profile = RenderProfile.load(args.render_profile)
        self.assertEqual(resolve_renderer_selection(args.renderer, profile), "RealTimePathTracing")

    def test_explicit_renderer_must_match_profile(self) -> None:
        profile = RenderProfile.load(DEFAULT_RENDER_PROFILES["PathTracing"])
        with self.assertRaisesRegex(ValueError, "conflicts"):
            resolve_renderer_selection("RealTimePathTracing", profile)


if __name__ == "__main__":
    unittest.main()
