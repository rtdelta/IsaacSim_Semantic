"""Pure-Python tests for CSV trajectory loading and interpolation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from excavator_joint_motion import ExcavatorJointMotion, JointTrajectory


CSV_TEXT = """time,cab,boom,small_arm,bucket
0.0,-2.4,-8.0,29.0,-8.0
1.0,7.6,2.0,19.0,12.0
2.0,-2.4,-8.0,29.0,-8.0
"""

ROOT_CSV_TEXT = """time,cab,boom,small_arm,bucket,root_quat_w,root_quat_x,root_quat_y,root_quat_z,root_roll_x_deg,root_pitch_y_deg,root_yaw_z_deg,root_world_x_m,root_world_y_m,root_world_z_m
0.0,0,0,0,0,1,0,0,0,0,0,0,0,0,0
1.0,10,20,30,40,0.7071067811865476,0,0,0.7071067811865476,0,0,90,2,4,6
"""


class JointTrajectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "trajectory.csv"
        self.path.write_text(CSV_TEXT, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loads_expected_keyframes(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        self.assertEqual(len(trajectory.keyframes), 3)
        self.assertAlmostEqual(trajectory.duration, 2.0)
        self.assertEqual(len(trajectory.sha256), 64)

    def test_linearly_interpolates_between_keyframes(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        trajectory_time, targets = trajectory.sample(0.5, "hold")
        self.assertAlmostEqual(trajectory_time, 0.5)
        self.assertAlmostEqual(targets["cab"], 2.6)
        self.assertAlmostEqual(targets["boom"], -3.0)
        self.assertAlmostEqual(targets["small_arm"], 24.0)
        self.assertAlmostEqual(targets["bucket"], 2.0)

    def test_loop_wraps_to_the_next_cycle(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        trajectory_time, targets = trajectory.sample(2.5, "loop")
        self.assertAlmostEqual(trajectory_time, 0.5)
        self.assertAlmostEqual(targets["cab"], 2.6)

    def test_hold_keeps_last_keyframe(self) -> None:
        trajectory = JointTrajectory.from_csv(self.path)
        trajectory_time, targets = trajectory.sample(5.0, "hold")
        self.assertAlmostEqual(trajectory_time, 2.0)
        self.assertAlmostEqual(targets["cab"], -2.4)

    def test_rejects_wrong_columns(self) -> None:
        self.path.write_text("time,cab\n0,0\n1,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "columns"):
            JointTrajectory.from_csv(self.path)

    def test_rejects_non_increasing_time(self) -> None:
        self.path.write_text(
            "time,cab,boom,small_arm,bucket\n0,0,0,0,0\n0,1,1,1,1\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            JointTrajectory.from_csv(self.path)

    def test_loads_and_interpolates_root_position_and_orientation(self) -> None:
        self.path.write_text(ROOT_CSV_TEXT, encoding="utf-8")
        trajectory = JointTrajectory.from_csv(self.path)

        sample = trajectory.sample_state(0.5, "hold")

        self.assertTrue(trajectory.has_root_pose)
        self.assertEqual(sample.root_position_meters, (1.0, 2.0, 3.0))
        self.assertAlmostEqual(sample.root_orientation_wxyz[0], 0.9238795325)
        self.assertAlmostEqual(sample.root_orientation_wxyz[3], 0.3826834324)

    def test_rejects_zero_root_quaternion(self) -> None:
        self.path.write_text(
            ROOT_CSV_TEXT.replace(",1,0,0,0,0,0,0,0,0,0", ",0,0,0,0,0,0,0,0,0,0", 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Invalid numeric value"):
            JointTrajectory.from_csv(self.path)


class FakeArticulationAdapter:
    def __init__(self, *, follow_commands: bool = True) -> None:
        self.ready = False
        self.follow_commands = follow_commands
        self.positions = (-2.4, -8.0, 29.0, -8.0)
        self.commands = []
        self.root_pose = ((10.0, 20.0, 30.0), (1.0, 0.0, 0.0, 0.0))
        self.root_commands = []
        self.shutdown_called = False

    def bind(self) -> None:
        self.ready = True

    def validate_runtime(self) -> None:
        if not self.ready:
            raise RuntimeError("not ready")

    def set_positions_degrees(self, values) -> None:
        values = tuple(float(value) for value in values)
        self.commands.append(values)
        if self.follow_commands:
            self.positions = values

    def get_positions_degrees(self):
        return self.positions

    def get_root_world_pose(self):
        return self.root_pose

    def set_root_world_pose(self, position, orientation) -> None:
        self.root_pose = (tuple(position), tuple(orientation))
        self.root_commands.append(self.root_pose)

    def binding_info(self):
        return {"bound": True, "ready": self.ready}

    def shutdown(self) -> None:
        self.shutdown_called = True
        self.ready = False


class ExcavatorJointMotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "trajectory.csv"
        self.path.write_text(CSV_TEXT, encoding="utf-8")
        self.profile = SimpleNamespace(
            logical_joint_names=("cab", "boom", "small_arm", "bucket"),
            readback_tolerance_degrees=0.05,
        )
        self.report = SimpleNamespace(
            articulation_root_path="/World/Joints/world_track_fixed_joint",
            joint_paths={
                "cab": "/World/Joints/track_operator_cab_joint",
                "boom": "/World/Joints/platform_boom_joint",
                "small_arm": "/World/Joints/boom_small_arm_joint",
                "bucket": "/World/Joints/small_arm_bucket_joint",
            },
            dof_names={
                "cab": "track_operator_cab_joint",
                "boom": "platform_boom_joint",
                "small_arm": "boom_small_arm_joint",
                "bucket": "small_arm_bucket_joint",
            },
            body_paths=tuple(f"/World/Body{index}" for index in range(5)),
            limits_degrees={name: (-100.0, 100.0) for name in self.profile.logical_joint_names},
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_motion(self, adapter=None, playback_mode="hold") -> ExcavatorJointMotion:
        return ExcavatorJointMotion(
            stage=object(),
            trajectory_path=self.path,
            joint_profile=self.profile,
            stage_report=self.report,
            playback_mode=playback_mode,
            adapter=adapter or FakeArticulationAdapter(),
        )

    def test_commands_ordered_interpolated_batch_and_records_readback(self) -> None:
        adapter = FakeArticulationAdapter()
        motion = self.make_motion(adapter)
        motion.bind()
        self.assertTrue(motion.ready)
        motion.initialize_runtime()

        motion.before_physics_step(0.5)
        motion.after_physics_step(0.5)

        self.assertEqual(adapter.commands, [(2.6, -3.0, 24.0, 2.0)])
        motion._body_transforms = lambda: {}
        state = motion.get_state()
        self.assertEqual(state["commanded_degrees"], state["actual_degrees"])
        self.assertEqual(state["target_degrees"], state["commanded_degrees"])
        self.assertEqual(set(state["position_error_degrees"].values()), {0.0})
        self.assertEqual(state["control_mode"], "articulation_direct_position")

    def test_rejects_readback_outside_profile_tolerance(self) -> None:
        adapter = FakeArticulationAdapter(follow_commands=False)
        motion = self.make_motion(adapter)
        motion.bind()
        motion.initialize_runtime()
        motion.before_physics_step(0.5)

        with self.assertRaisesRegex(RuntimeError, "readback exceeded"):
            motion.after_physics_step(0.5)

    def test_loop_rejects_a_non_closed_recorder_trajectory(self) -> None:
        self.path.write_text(
            "time,cab,boom,small_arm,bucket\n0,0,0,0,0\n1,1,2,3,4\n",
            encoding="utf-8",
        )
        motion = self.make_motion(playback_mode="loop")
        with self.assertRaisesRegex(ValueError, "non-closed trajectories"):
            motion.bind()

    def test_shutdown_releases_adapter(self) -> None:
        adapter = FakeArticulationAdapter()
        motion = self.make_motion(adapter)
        motion.bind()
        motion.initialize_runtime()
        motion.shutdown()
        self.assertTrue(adapter.shutdown_called)

    def test_commands_and_records_absolute_root_pose(self) -> None:
        self.path.write_text(ROOT_CSV_TEXT, encoding="utf-8")
        self.profile.require_fixed_base = False
        self.profile.require_floating_base = True
        self.profile.root_pose_playback_supported = True
        root_config = SimpleNamespace(
            enabled=True,
            coordinate_mode="absolute_world",
            apply_policy="authoritative_pose",
            position_tolerance_meters=0.001,
            orientation_tolerance_degrees=0.05,
        )
        adapter = FakeArticulationAdapter()
        motion = ExcavatorJointMotion(
            stage=object(),
            trajectory_path=self.path,
            joint_profile=self.profile,
            stage_report=self.report,
            playback_mode="hold",
            root_pose_playback=root_config,
            adapter=adapter,
        )
        motion.bind()
        motion.initialize_runtime()

        motion.before_physics_step(0.5)
        motion.after_physics_step(0.5)

        self.assertEqual(adapter.root_commands[-1][0], (1.0, 2.0, 3.0))
        motion._body_transforms = lambda: {"root": [1.0] * 16}
        root_state = motion.get_state()["root_pose"]
        self.assertEqual(root_state["capture_position_meters"], (1.0, 2.0, 3.0))
        self.assertAlmostEqual(root_state["orientation_error_degrees"], 0.0)
        provenance = motion.trajectory_info()["metadata_provenance"]
        self.assertFalse(provenance["present"])
        self.assertEqual(
            provenance["source_contract_basis"],
            "csv_absolute_world_user_assertion",
        )
        coordinate_contract = motion.binding_info()["root_pose_playback"][
            "coordinate_contract"
        ]
        self.assertIsNone(coordinate_contract["source_stage_path"])
        self.assertEqual(
            coordinate_contract["source_contract_basis"],
            "csv_absolute_world_user_assertion",
        )

    def test_relative_root_pose_reanchors_recorded_transform(self) -> None:
        self.path.write_text(ROOT_CSV_TEXT, encoding="utf-8")
        self.profile.require_fixed_base = False
        self.profile.require_floating_base = True
        self.profile.root_pose_playback_supported = True
        adapter = FakeArticulationAdapter()
        motion = ExcavatorJointMotion(
            stage=object(),
            trajectory_path=self.path,
            joint_profile=self.profile,
            stage_report=self.report,
            playback_mode="hold",
            root_pose_playback=SimpleNamespace(
                enabled=True,
                coordinate_mode="relative_to_initial",
                apply_policy="authoritative_pose",
                position_tolerance_meters=0.001,
                orientation_tolerance_degrees=0.05,
            ),
            adapter=adapter,
        )
        motion.bind()
        motion.initialize_runtime()

        motion.before_physics_step(1.0)
        motion.after_physics_step(1.0)

        self.assertEqual(adapter.root_commands[-1][0], (12.0, 24.0, 36.0))
        self.assertAlmostEqual(adapter.root_commands[-1][1][0], 0.7071067812)
        self.assertAlmostEqual(adapter.root_commands[-1][1][3], 0.7071067812)


if __name__ == "__main__":
    unittest.main()
