"""Tests for semantic state-leak detection rules."""

from __future__ import annotations

import unittest

import numpy as np

from capture_context import CaptureVariant
from capture_launch_config import SemanticContentRule, VariantValidationConfig
from semantic_content_validation import validate_semantic_content


def validation_config() -> VariantValidationConfig:
    return VariantValidationConfig(
        enabled=True,
        full_scene=SemanticContentRule(
            allowed_labels=None,
            required_any_labels=("boom", "arm"),
            forbidden_labels=(),
            allow_empty_target=False,
        ),
        excavator_only=SemanticContentRule(
            allowed_labels=("boom", "arm", "front_tooth"),
            required_any_labels=("boom", "arm"),
            forbidden_labels=(),
            allow_empty_target=False,
        ),
        front_teeth_only=SemanticContentRule(
            allowed_labels=("front_tooth",),
            required_any_labels=("front_tooth",),
            forbidden_labels=("boom", "arm"),
            allow_empty_target=True,
        ),
    )


class SemanticContentValidationTests(unittest.TestCase):
    id_to_label = {0: "BACKGROUND", 1: "boom", 2: "arm", 5: "front_tooth"}

    def validate(self, variant: CaptureVariant, values: list[list[int]]):
        return validate_semantic_content(
            config=validation_config(),
            variant=variant,
            dataset_ids=np.asarray(values, dtype=np.uint16),
            id_to_label=self.id_to_label,
            background_id=0,
        )

    def test_full_scene_rejects_stale_front_only_pixels(self) -> None:
        result = self.validate(CaptureVariant.FULL_SCENE, [[0, 5], [5, 0]])
        self.assertFalse(result.passed)
        self.assertIn("required_any_labels", result.errors[0])

    def test_full_scene_accepts_non_front_excavator_label(self) -> None:
        result = self.validate(CaptureVariant.FULL_SCENE, [[0, 5], [1, 0]])
        self.assertTrue(result.passed)

    def test_front_only_rejects_leaked_full_scene_label(self) -> None:
        result = self.validate(CaptureVariant.FRONT_TEETH_ONLY, [[0, 5], [1, 0]])
        self.assertFalse(result.passed)
        self.assertTrue(any("unexpected labels" in error for error in result.errors))
        self.assertTrue(any("forbidden labels" in error for error in result.errors))

    def test_excavator_only_rejects_stale_front_only_pixels(self) -> None:
        result = self.validate(CaptureVariant.EXCAVATOR_ONLY, [[0, 5], [5, 0]])
        self.assertFalse(result.passed)
        self.assertIn("required_any_labels", result.errors[0])

    def test_front_only_can_be_empty_when_teeth_are_offscreen(self) -> None:
        result = self.validate(CaptureVariant.FRONT_TEETH_ONLY, [[0, 0], [0, 0]])
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
