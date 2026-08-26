import unittest
from dataclasses import replace

from semantic_world_v04.compiler import JobCompiler, SegmentPlanner
from semantic_world_v04.core.models import SegmentSpec, SegmentStatus

from helpers import make_project


class SegmentPlannerTests(unittest.TestCase):
    def test_non_divisible_capture_produces_complete_deterministic_plan(self) -> None:
        project = make_project()
        project.capture.start_frame = 5
        project.capture.frame_count = 23
        project.capture.segment_frames = 10
        job = JobCompiler().compile(project, job_id="job-segments")

        segments = SegmentPlanner().plan(job)

        self.assertEqual([5, 15, 25], [item.start_frame for item in segments])
        self.assertEqual([10, 10, 3], [item.frame_count for item in segments])
        self.assertEqual([20, 20, 6], [item.expected_capture_groups for item in segments])
        self.assertEqual(
            ["absolute_seek"] * 3,
            [item.motion_positioning for item in segments],
        )
        self.assertEqual(
            [item.to_dict() for item in segments],
            [item.to_dict() for item in SegmentPlanner().plan(job)],
        )

    def test_auto_falls_back_to_single_worker_for_non_seek_motion(self) -> None:
        project = make_project()
        project.capture.frame_count = 23
        project.capture.segment_frames = 10
        project.motion.plugin = "csv_articulation"
        project.motion.source_path = "trajectory.csv"
        project.motion.supports_absolute_seek = False
        project.motion.options = {
            "articulation_prim_path": "/World/Robot",
            "joint_columns": {"joint": "joint"},
        }
        job = JobCompiler().compile(project, job_id="job-single")

        segments = SegmentPlanner().plan(job)

        self.assertEqual(1, len(segments))
        self.assertEqual("single_worker", segments[0].motion_positioning)
        self.assertEqual(23, segments[0].frame_count)

    def test_replay_strategy_keeps_segments_for_non_seek_motion(self) -> None:
        project = make_project()
        project.capture.frame_count = 23
        project.capture.segment_frames = 10
        project.execution.segmentation_strategy = "replay_from_zero"
        project.motion.plugin = "csv_articulation"
        project.motion.source_path = "trajectory.csv"
        project.motion.options = {
            "articulation_prim_path": "/World/Robot",
            "joint_columns": {"joint": "joint"},
        }
        job = JobCompiler().compile(project, job_id="job-replay")

        segments = SegmentPlanner().plan(job)

        self.assertEqual(3, len(segments))
        self.assertTrue(
            all(item.motion_positioning == "replay_from_zero" for item in segments)
        )

    def test_tampered_segment_range_is_rejected(self) -> None:
        job = JobCompiler().compile(make_project(), job_id="job-tamper")
        segments = SegmentPlanner().plan(job)
        segments[0] = replace(segments[0], end_frame_exclusive=999)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            SegmentPlanner.validate(job, segments)

    def test_non_positive_capture_and_tampered_group_count_are_rejected(self) -> None:
        project = make_project()
        job = JobCompiler().compile(project, job_id="job-invalid-plan")
        job.project.capture.frame_count = 0
        with self.assertRaisesRegex(ValueError, "positive"):
            SegmentPlanner().plan(job)

        project.capture.frame_count = 1
        valid_job = JobCompiler().compile(project, job_id="job-group-count")
        segments = SegmentPlanner().plan(valid_job)
        segments[0] = replace(segments[0], expected_capture_groups=999)
        with self.assertRaisesRegex(ValueError, "expected_capture_groups"):
            SegmentPlanner.validate(valid_job, segments)

    def test_segment_models_are_strict_and_round_trip(self) -> None:
        job = JobCompiler().compile(make_project(), job_id="job-model")
        segment = SegmentPlanner().plan(job)[0]
        self.assertEqual(segment, SegmentSpec.from_dict(segment.to_dict()))
        status = SegmentStatus(
            job_id=job.job_id,
            segment_id=segment.segment_id,
            capture_groups_total=segment.expected_capture_groups,
        )
        self.assertEqual(status, SegmentStatus.from_dict(status.to_dict()))
        invalid = segment.to_dict()
        invalid["typo"] = True
        with self.assertRaises(Exception):
            SegmentSpec.from_dict(invalid)


if __name__ == "__main__":
    unittest.main()
