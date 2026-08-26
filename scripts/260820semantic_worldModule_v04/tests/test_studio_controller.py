import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from semantic_world_v04.core.models import JobStatus, SegmentStatus
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.output.segment_store import SegmentStatusStore
from semantic_world_v04.stage import PrimSummary, StageIndex
from semantic_world_v04.studio import StudioController


class FakeSupervisor:
    def __init__(self) -> None:
        self.submitted = None
        self.started = None

    def submit(self, job):
        self.submitted = job
        return JobStatus(job_id=job.job_id, state="queued")

    def start(self, job_id, output_root):
        self.started = (job_id, Path(output_root))
        return JobStatus(job_id=job_id, state="preflight", pid=123)

    def status(self, job_id, output_root):
        return JobStatus(
            job_id=job_id,
            state="running",
            frame_current=1,
            frame_total=2,
        )

    def stop(self, job_id, output_root):
        return JobStatus(job_id=job_id, state="stopping")


class StudioControllerTests(unittest.TestCase):
    def test_run_headless_delegates_to_same_host_supervisor(self) -> None:
        fake = FakeSupervisor()
        controller = StudioController(supervisor=fake)
        controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary("/World/Camera", "Camera"),
                ]
            )
        )
        controller.add_camera_from_stage("/World/Camera", "camera")
        with tempfile.TemporaryDirectory() as temp:
            controller.project.output.root_dir = str(Path(temp) / "output")
            controller.save_project(Path(temp) / "demo.swproject")
            status = controller.run_headless(job_id="job-ui")

            self.assertEqual("preflight", status.state)
            self.assertEqual("job-ui", fake.submitted.job_id)
            self.assertEqual("job-ui", fake.started[0])
            refreshed = controller.job_status()
            self.assertEqual("running", refreshed.state)
            stopped = controller.stop_job()
            self.assertEqual("stopping", stopped.state)

    def test_camera_discovery_project_save_and_compile(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo",
            name="Demo",
            usd_path="scene.usda",
        )
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary("/World", "Xform"),
                    PrimSummary(
                        "/World/Camera",
                        "Camera",
                        attributes={"focalLength": 18.0},
                    ),
                ]
            )
        )
        self.assertEqual(["/World/Camera"], controller.discover_cameras())
        sensor = controller.add_camera_from_stage("/World/Camera")
        self.assertEqual("stage", sensor.parameter_sources["focalLength"])

        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "demo.swproject"
            controller.save_project(project_dir)
            job = controller.compile_job(job_id="job-test")
            self.assertTrue(
                (project_dir / "jobs/job-test/job_spec.json").is_file()
            )
            self.assertTrue(controller.compiler.verify(job))

    def test_include_variant_defaults_to_semantic_only(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary("/World", "Xform"),
                    PrimSummary("/World/Camera", "Camera"),
                ]
            )
        )
        controller.add_camera_from_stage("/World/Camera", "camera")
        variant = controller.add_include_variant("isolated", ["/World"])
        self.assertEqual(
            ["semantic_id", "semantic_color"],
            variant.modalities_by_sensor["camera"],
        )

    def test_sensor_editing_and_modality_matrix_are_project_services(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary("/World/Camera", "Camera"),
                ]
            )
        )
        controller.add_camera_from_stage("/World/Camera", "camera")
        copied = controller.copy_sensor("camera")
        self.assertEqual("camera_2", copied.sensor_id)
        controller.set_sensor_overrides("camera", {"focalLength": 24.0})
        self.assertEqual(
            "override", controller.get_sensor("camera").parameter_sources["focalLength"]
        )
        controller.set_modalities("full_scene", "camera", ["semantic_id"])
        self.assertEqual(
            ["semantic_id"],
            controller.get_variant("full_scene").modalities_by_sensor["camera"],
        )
        controller.delete_sensor("camera_2")
        self.assertEqual(["camera"], [item.sensor_id for item in controller.project.sensors])

    def test_production_configuration_services_update_typed_models(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        render = controller.set_render_profile(
            renderer="PathTracing",
            resolution_width=1280,
            resolution_height=720,
            warmup_frames=16,
            rt_subframes=8,
            spp_per_frame=8,
            total_spp=64,
            max_bounces=4,
            denoiser=True,
            settings={"/rtx/test": 1},
        )
        capture = controller.set_capture_schedule(
            physics_hz=60,
            capture_fps=10,
            start_frame=20,
            frame_count=100,
            capture_initial_frame=True,
            segment_frames=25,
        )
        motion = controller.set_motion_spec(
            plugin="csv_articulation",
            source_path="trajectory.csv",
            supports_absolute_seek=True,
            options={
                "articulation_prim_path": "/World/Robot",
                "joint_columns": {"joint": "joint_csv"},
            },
        )
        semantics = controller.set_semantic_profile(
            mapping_path="mapping.json",
            label_attribute="class",
            background_id=7,
            options={"filter": "class:*"},
        )
        execution = controller.set_execution_policy(
            segmentation_strategy="auto",
            heartbeat_timeout_seconds=90,
            no_progress_timeout_seconds=480,
            segment_start_timeout_seconds=240,
            graceful_stop_timeout_seconds=20,
            telemetry_interval_seconds=4,
        )

        self.assertEqual("PathTracing", render.renderer)
        self.assertEqual(1280, render.resolution_width)
        self.assertEqual(100, capture.frame_count)
        self.assertTrue(motion.supports_absolute_seek)
        self.assertEqual(7, semantics.background_id)
        self.assertEqual(90, execution.heartbeat_timeout_seconds)
        self.assertTrue(controller.dirty)

    def test_segment_and_failure_diagnostics_are_available_to_studio(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "output"
            job_dir = root / "job-diagnostics"
            segment_dir = job_dir / "segments" / "segment_000000"
            SegmentStatusStore(segment_dir / "status.json").write(
                SegmentStatus(
                    job_id="job-diagnostics",
                    segment_id="segment_000000",
                    state="failed",
                    capture_groups_current=2,
                    capture_groups_total=4,
                )
            )
            atomic_write_json(
                segment_dir / "segment_spec.json",
                {
                    "start_frame": 10,
                    "frame_count": 2,
                    "end_frame_exclusive": 12,
                    "motion_positioning": "absolute_seek",
                },
            )
            atomic_write_json(
                job_dir / "failure_report.json",
                {"failure_code": "worker_exit", "message": "test"},
            )
            controller.last_job = type("LastJob", (), {"job_id": "job-diagnostics"})()
            controller.last_output_root = root

            segments = controller.list_segments()
            self.assertEqual("failed", segments[0]["state"])
            self.assertEqual(10, segments[0]["start_frame"])
            report = controller.read_failure_report()
            self.assertEqual("worker_exit", report["failure_code"])

    def test_preflight_estimates_capture_and_lists_compiled_jobs(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary(
                        "/World/Camera",
                        "Camera",
                        attributes={"focalLength": 24.0},
                    ),
                ]
            )
        )
        controller.add_camera_from_stage("/World/Camera", "camera")
        controller.project.capture.frame_count = 3
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "demo.swproject"
            controller.project.output.root_dir = str(Path(temp) / "output")
            controller.save_project(project_dir)
            (project_dir / "scene.usda").write_text("#usda 1.0\n", encoding="utf-8")
            summary = controller.preflight_summary()
            self.assertTrue(summary["can_run"])
            self.assertTrue(summary["stage_indexed"])
            self.assertEqual(3, summary["estimate"]["capture_groups"])
            self.assertGreater(summary["estimate"]["estimated_bytes"], 0)

            controller.compile_job(job_id="job-history")
            jobs = controller.list_jobs()
            self.assertEqual("job-history", jobs[0]["job_id"])
            self.assertEqual("compiled", jobs[0]["state"])

    def test_preflight_blocks_missing_or_unindexed_stage(self) -> None:
        controller = StudioController()
        controller.new_project(
            project_id="demo", name="Demo", usd_path="missing.usda"
        )
        summary = controller.preflight_summary()
        self.assertFalse(summary["can_run"])
        self.assertIn(
            "stage.not_indexed", {item["code"] for item in summary["issues"]}
        )
        self.assertIn(
            "preflight.file_missing",
            {item["code"] for item in summary["issues"]},
        )

    def test_reapplying_unchanged_production_config_does_not_mark_dirty(self) -> None:
        controller = StudioController()
        project = controller.new_project(
            project_id="demo", name="Demo", usd_path="scene.usda"
        )
        with tempfile.TemporaryDirectory() as temp:
            controller.save_project(Path(temp) / "demo.swproject")
            controller.set_render_profile(**asdict(project.render))
            controller.set_capture_schedule(**asdict(project.capture))
            controller.set_execution_policy(**asdict(project.execution))
            controller.set_motion_spec(**asdict(project.motion))
            controller.set_semantic_profile(**asdict(project.semantics))
            self.assertFalse(controller.dirty)


if __name__ == "__main__":
    unittest.main()
