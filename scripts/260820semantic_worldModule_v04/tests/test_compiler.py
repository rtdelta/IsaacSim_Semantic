import unittest
from pathlib import Path

from semantic_world_v04.compiler import JobCompiler, ProjectValidator
from semantic_world_v04.core.errors import ValidationFailed
from semantic_world_v04.project import ProjectPathResolver
from semantic_world_v04.stage import PrimSummary, StageIndex

from helpers import make_project


class CompilerTests(unittest.TestCase):
    def test_deterministic_digest_and_integrity(self) -> None:
        project = make_project()
        compiler = JobCompiler()
        first = compiler.compile(
            project,
            source_project_path="/projects/demo.swproject",
            job_id="job-a",
            compiled_at_utc="2026-08-20T00:00:00Z",
        )
        second = compiler.compile(
            project,
            source_project_path="/projects/demo.swproject",
            job_id="job-b",
            compiled_at_utc="2026-08-21T00:00:00Z",
        )
        self.assertEqual(first.content_digest, second.content_digest)
        self.assertTrue(compiler.verify(first))

        first.project.render.resolution_width = 999
        self.assertFalse(compiler.verify(first))

    def test_duplicate_sensor_blocks_compilation(self) -> None:
        project = make_project()
        project.sensors.append(project.sensors[0])
        with self.assertRaises(ValidationFailed):
            JobCompiler().compile(project)

    def test_unknown_modality_reference_is_reported(self) -> None:
        project = make_project()
        project.variants[0].modalities_by_sensor["boom_camera"].append("depth")
        issues = ProjectValidator().validate(project)
        self.assertIn("variant.modality_reference", {issue.code for issue in issues})

    def test_stage_validation_confirms_camera_type(self) -> None:
        project = make_project()
        stage = StageIndex(
            [
                PrimSummary("/", "PseudoRoot"),
                PrimSummary("/World", "Xform"),
                PrimSummary("/World/Excavator", "Xform"),
                PrimSummary("/World/Excavator/Camera", "Xform"),
                PrimSummary("/World/Light", "DistantLight"),
            ]
        )
        issues = ProjectValidator().validate(project, stage)
        self.assertIn("sensor.prim_type", {issue.code for issue in issues})

    def test_semantic_only_variant_has_no_rgb_request(self) -> None:
        project = make_project()
        requested = project.variants[1].modalities_by_sensor["boom_camera"]
        self.assertEqual(["semantic_id", "semantic_color"], requested)
        self.assertNotIn("rgb", requested)

    def test_compiler_freezes_stage_camera_parameters_and_relative_paths(self) -> None:
        project = make_project()
        stage = StageIndex(
            [
                PrimSummary("/", "PseudoRoot"),
                PrimSummary("/World", "Xform"),
                PrimSummary("/World/Excavator", "Xform"),
                PrimSummary(
                    "/World/Excavator/Camera",
                    "Camera",
                    attributes={"focalLength": 35.0},
                ),
                PrimSummary("/World/Light", "DistantLight"),
            ]
        )
        job = JobCompiler().compile(
            project,
            source_project_path="/projects/demo.swproject",
            stage_index=stage,
            job_id="job-resolved",
        )
        self.assertEqual(
            ProjectPathResolver.resolve(
                "scene.usda", Path("/projects/demo.swproject")
            ),
            job.project.stage.usd_path,
        )
        self.assertEqual(35.0, job.project.sensors[0].parameters["focalLength"])
        self.assertEqual(
            "stage", job.project.sensors[0].parameter_sources["focalLength"]
        )

    def test_unsafe_identifier_is_rejected(self) -> None:
        project = make_project()
        project.sensors[0].sensor_id = "../camera"
        with self.assertRaises(ValidationFailed):
            JobCompiler().compile(project)

    def test_invalid_csv_motion_is_reported_before_runtime(self) -> None:
        project = make_project()
        project.motion.plugin = "csv_articulation"
        project.motion.source_path = "trajectory.csv"
        project.motion.options = {}
        issues = ProjectValidator().validate(project)
        codes = {issue.code for issue in issues}
        self.assertIn("motion.articulation_prim_path", codes)
        self.assertIn("motion.joint_columns", codes)


if __name__ == "__main__":
    unittest.main()
