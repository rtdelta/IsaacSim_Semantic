"""Pure-Python tests for the versioned articulation-control profile."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from joint_control_profile import JointControlProfile, JointControlProfileError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = PROJECT_ROOT / "configs" / "excavator_four_joint_articulation.json"


class JointControlProfileTests(unittest.TestCase):
    def test_default_profile_exposes_auditable_four_joint_contract(self) -> None:
        profile = JointControlProfile.load(DEFAULT_PROFILE)

        self.assertEqual(
            profile.logical_joint_names, ("cab", "boom", "small_arm", "bucket")
        )
        self.assertTrue(profile.require_fixed_base)
        self.assertTrue(profile.forbid_angular_drives)
        self.assertEqual(profile.readback_tolerance_degrees, 0.05)
        self.assertEqual(
            profile.articulation_root_path, "/World/Joints/world_track_fixed_joint"
        )
        self.assertEqual(len(profile.source_sha256), 64)
        self.assertEqual(profile.source_path, DEFAULT_PROFILE.resolve())
        snapshot = profile.to_dict()
        self.assertEqual(snapshot["sha256"], profile.source_sha256)
        self.assertEqual(snapshot["logical_joint_names"], list(profile.logical_joint_names))
        self.assertTrue(all(joint.candidate_names for joint in profile.joints))
        self.assertTrue(all(joint.candidate_paths for joint in profile.joints))

    def test_rejects_a_profile_without_exactly_four_joints(self) -> None:
        raw = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
        raw["joints"] = raw["joints"][:3]

        with self.assertRaisesRegex(JointControlProfileError, "exactly 4 joints"):
            self._load_raw(raw)

    def test_rejects_a_joint_without_name_or_path_candidates(self) -> None:
        raw = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
        raw["joints"][0]["candidate_names"] = []
        raw["joints"][0]["candidate_paths"] = []

        with self.assertRaisesRegex(JointControlProfileError, "needs candidate_names"):
            self._load_raw(raw)

    def test_rejects_negative_safety_margin(self) -> None:
        raw = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
        raw["joints"][0]["safety_margin_degrees"] = -0.1

        with self.assertRaisesRegex(JointControlProfileError, "finite and non-negative"):
            self._load_raw(raw)

    def test_optional_metadata_can_be_absent(self) -> None:
        profile = JointControlProfile.load(DEFAULT_PROFILE)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "trajectory.csv"
            csv_path.write_text("time,cab,boom,small_arm,bucket\n", encoding="utf-8")
            self.assertIsNone(profile.load_and_validate_trajectory_metadata(csv_path))
            with self.assertRaises(FileNotFoundError):
                profile.load_and_validate_trajectory_metadata(csv_path, required=True)

    def test_accepts_compatible_recorder_metadata(self) -> None:
        profile = JointControlProfile.load(DEFAULT_PROFILE)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "trajectory.csv"
            csv_path.write_text("time,cab,boom,small_arm,bucket\n", encoding="utf-8")
            sidecar = csv_path.with_name("trajectory.metadata.json")
            metadata = self._valid_metadata(profile)
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")

            loaded = profile.load_and_validate_trajectory_metadata(csv_path)

            self.assertEqual(loaded, metadata)
            self.assertEqual(profile.trajectory_metadata_path(csv_path), sidecar.resolve())

    def test_rejects_incomplete_wrong_order_or_wrong_unit_metadata(self) -> None:
        profile = JointControlProfile.load(DEFAULT_PROFILE)
        cases = (
            ({"completed": False}, "completed must be true"),
            ({"joint_order": ["boom", "cab", "small_arm", "bucket"]}, "joint_order"),
            ({"angle_unit": "radian"}, "angle_unit"),
            ({"control_mode": "angular_drive"}, "control_mode"),
            ({"profile": "another_excavator"}, "does not match"),
        )
        for override, message in cases:
            with self.subTest(override=override):
                with tempfile.TemporaryDirectory() as directory:
                    csv_path = Path(directory) / "trajectory.csv"
                    csv_path.write_text("placeholder", encoding="utf-8")
                    metadata = self._valid_metadata(profile)
                    metadata.update(override)
                    metadata_path = Path(directory) / "custom-sidecar.json"
                    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                    with self.assertRaisesRegex(JointControlProfileError, message):
                        profile.load_and_validate_trajectory_metadata(
                            csv_path, metadata_path=metadata_path
                        )

    @staticmethod
    def _valid_metadata(profile: JointControlProfile) -> dict[str, object]:
        return {
            "completed": True,
            "joint_order": list(profile.logical_joint_names),
            "angle_unit": "degree",
            "control_mode": "articulation_direct_position",
            "profile": profile.profile_name,
        }

    @staticmethod
    def _load_raw(raw: dict[str, object]) -> JointControlProfile:
        temporary = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False
        )
        try:
            json.dump(raw, temporary)
            temporary.close()
            return JointControlProfile.load(temporary.name)
        finally:
            Path(temporary.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
