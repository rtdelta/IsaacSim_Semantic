import tempfile
import unittest
from pathlib import Path

import numpy as np

from semantic_world_v04.compiler import JobCompiler, ProjectValidator, SegmentPlanner
from semantic_world_v04.core.models import JobSpec, ModalityDefinition, SensorDefinition
from semantic_world_v04.core.serde import content_sha256
from semantic_world_v04.core.sensor_models import CaptureBatchKey, RigDefinition
from semantic_world_v04.output import (
    AtomicCaptureBatchWriter,
    BatchLedger,
    FrameLedger,
    validate_encoded_artifact,
)
from semantic_world_v04.plugins import build_default_registry
from semantic_world_v04.plugins.sensors.fisheye_camera import FisheyeCameraPlugin
from semantic_world_v04.plugins.sensors.rtx_lidar import RtxLidarPlugin
from semantic_world_v04.runtime.encoding import (
    encode_npy,
    encode_npz,
    encode_point_cloud_ply,
)
from semantic_world_v04.runtime.lidar_driver import RtxLidarRuntimeDriver
from semantic_world_v04.stage import PrimSummary, StageIndex
from semantic_world_v04.studio import StudioController

from helpers import make_project


class V043SensorPlatformTests(unittest.TestCase):
    def test_registry_discovers_manifests_and_parameter_schemas(self) -> None:
        registry = build_default_registry()
        manifest = registry.manifest("sensor", "fisheye_camera")
        self.assertEqual(2, manifest.contract_version)
        self.assertEqual("1.0.0", manifest.plugin_version)
        schema = registry.sensor("rtx_lidar").parameter_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("max_range", schema["properties"])

    def test_parameter_schema_rejects_unknown_and_wrong_type_overrides(self) -> None:
        controller = StudioController()
        project = controller.new_project(
            project_id="schema-demo", name="Schema Demo", usd_path="scene.usd"
        )
        project.sensors.append(
            SensorDefinition("lidar", "rtx_lidar", "/World/Lidar")
        )
        with self.assertRaisesRegex(ValueError, "unknown parameter"):
            controller.set_sensor_overrides("lidar", {"max_ragne": 100.0})
        with self.assertRaisesRegex(ValueError, "expected number"):
            controller.set_sensor_overrides("lidar", {"max_range": "far"})
        controller.set_sensor_overrides("lidar", {"max_range": 100.0})
        self.assertEqual(100.0, project.sensors[0].parameters["max_range"])

    def test_fisheye_and_lidar_are_discovered_from_stage_data(self) -> None:
        fisheye = PrimSummary(
            "/World/Fisheye",
            "Camera",
            attributes={
                "cameraProjectionType": "fisheyePolynomial",
                "fisheyeMaxFOV": 180.0,
            },
        )
        lidar = PrimSummary(
            "/World/Lidar",
            "Camera",
            attributes={"omni:sensor:rotationRate": 10.0},
            applied_schemas=("IsaacRtxLidarSensorAPI",),
        )
        self.assertTrue(FisheyeCameraPlugin().matches_prim(fisheye))
        self.assertTrue(RtxLidarPlugin().matches_prim(lidar))
        definition = FisheyeCameraPlugin().definition_from_prim("fish", fisheye)
        self.assertEqual("stage", definition.parameter_sources["fisheyeMaxFOV"])

    def test_project_rig_round_trips_and_validates_membership(self) -> None:
        project = make_project()
        project.rigs = [RigDefinition("front_rig", ["boom_camera"])]
        restored = type(project).from_dict(project.to_dict())
        self.assertEqual(project, restored)
        self.assertFalse(
            [
                issue
                for issue in ProjectValidator().validate(project)
                if issue.severity == "error"
            ]
        )
        compiled = JobCompiler().compile(project, job_id="rig-job")
        self.assertEqual(
            "front_rig", compiled.project.sensors[0].sync_group_id
        )
        self.assertFalse(
            [
                issue
                for issue in ProjectValidator().validate(compiled.project)
                if issue.severity == "error"
            ]
        )

        project.rigs.append(RigDefinition("other", ["boom_camera"]))
        codes = {issue.code for issue in ProjectValidator().validate(project)}
        self.assertIn("rig.multiple_membership", codes)

    def test_v042_job_digest_remains_readable_after_schema_v2_upgrade(self) -> None:
        compiled = JobCompiler().compile(make_project(), job_id="legacy-job")
        legacy_project = compiled.project.to_dict()
        legacy_project["schema_version"] = 1
        legacy_project.pop("execution")
        legacy_project.pop("rigs")
        for sensor in legacy_project["sensors"]:
            sensor.pop("plugin_version")
            sensor.pop("backend")
            sensor.pop("sync_group_id")
        for modality in legacy_project["modalities"]:
            modality.pop("plugin_version")
        payload = {
            "schema_version": 1,
            "source_project_path": compiled.source_project_path,
            "project": legacy_project,
        }
        document = compiled.to_dict()
        document["schema_version"] = 1
        document["project"] = legacy_project
        document["content_digest"] = content_sha256(payload)
        restored = JobSpec.from_dict(document)
        self.assertEqual(1, restored.schema_version)
        self.assertTrue(JobCompiler.verify(restored))

    def test_batch_marker_is_written_after_member_frame_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = FrameLedger(root / "ledger.jsonl")
            batches = BatchLedger(root / "batch_ledger.jsonl")
            writer = AtomicCaptureBatchWriter(root, frames, batches)
            key = CaptureBatchKey(3, "full", "front_rig")
            entry = writer.commit(
                key=key,
                simulation_time=0.3,
                members={
                    "left": {
                        "requested_modalities": ["rgb"],
                        "artifacts": {"sensors/left/full/rgb/000003.png": b"left"},
                    },
                    "right": {
                        "requested_modalities": ["rgb"],
                        "artifacts": {"sensors/right/full/rgb/000003.png": b"right"},
                    },
                },
            )
            self.assertEqual(["left", "right"], entry.sensor_ids)
            self.assertTrue(writer.is_committed(key))
            self.assertEqual(2, len(list(frames.entries())))
            self.assertEqual(1, len(list(batches.entries())))

            retry = writer.commit(
                key=key,
                simulation_time=99.0,
                members={
                    "left": {"requested_modalities": ["rgb"], "artifacts": {}},
                    "right": {"requested_modalities": ["rgb"], "artifacts": {}},
                },
            )
            self.assertEqual(entry, retry)

    def test_batch_reconciles_preexisting_frame_entries(self) -> None:
        from semantic_world_v04.output import AtomicFrameWriter

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = FrameLedger(root / "ledger.jsonl")
            AtomicFrameWriter(root, frames).commit(
                frame_index=0,
                sensor_id="left",
                variant_id="full",
                simulation_time=0.0,
                requested_modalities=["rgb"],
                artifacts={"sensors/left/full/rgb/000000.png": b"old"},
            )
            batches = BatchLedger(root / "batch_ledger.jsonl")
            writer = AtomicCaptureBatchWriter(root, frames, batches)
            writer.commit(
                key=CaptureBatchKey(0, "full", "rig"),
                simulation_time=0.0,
                members={
                    "left": {"requested_modalities": ["rgb"], "artifacts": {}},
                    "right": {
                        "requested_modalities": ["rgb"],
                        "artifacts": {"sensors/right/full/rgb/000000.png": b"new"},
                    },
                },
            )
            self.assertEqual(
                b"old", (root / "sensors/left/full/rgb/000000.png").read_bytes()
            )
            self.assertEqual(2, len(list(frames.entries())))

    def test_new_artifact_encoders_are_content_validated(self) -> None:
        depth = np.ones((3, 4), dtype=np.float32)
        validate_encoded_artifact(
            "depth_linear",
            encode_npy(depth),
            expected_resolution=(4, 3),
        )
        cloud = {"points": np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32)}
        validate_encoded_artifact("point_cloud", encode_npz(cloud))
        validate_encoded_artifact(
            "point_cloud_ply", encode_point_cloud_ply(cloud)
        )
        with self.assertRaisesRegex(ValueError, "floating"):
            validate_encoded_artifact(
                "depth_linear", encode_npy(depth.astype(np.uint16))
            )

    def test_lidar_time_model_forces_replay_from_zero_segments(self) -> None:
        project = make_project()
        project.sensors = [
            SensorDefinition(
                sensor_id="lidar",
                plugin="rtx_lidar",
                prim_path="/World/Lidar",
            )
        ]
        project.modalities = [ModalityDefinition("point_cloud", "point_cloud")]
        for variant in project.variants:
            variant.modalities_by_sensor = {"lidar": ["point_cloud"]}
        project.capture.frame_count = 5
        project.capture.segment_frames = 2
        project.motion.supports_absolute_seek = True
        job = JobCompiler().compile(project, job_id="lidar-job")
        segments = SegmentPlanner().plan(job)
        self.assertEqual(3, len(segments))
        self.assertTrue(
            all(item.motion_positioning == "replay_from_zero" for item in segments)
        )

    def test_lidar_driver_normalizes_device_arrays_and_aux_fields(self) -> None:
        class DeviceArray:
            def __init__(self, value) -> None:
                self.value = np.asarray(value)

            def numpy(self):
                return self.value

        driver = RtxLidarRuntimeDriver(
            SensorDefinition("lidar", "rtx_lidar", "/World/Lidar"),
            modalities=["point_cloud"],
        )
        cloud = driver._normalize_cloud(
            {
                "data": DeviceArray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
                "intensity": DeviceArray([0.25, 0.75]),
                "info": {"transform": np.eye(4)},
            }
        )
        np.testing.assert_allclose(
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], cloud["points"]
        )
        np.testing.assert_allclose([0.25, 0.75], cloud["intensity"])
        self.assertTrue(driver.requires_continuous_history)

    def test_studio_catalog_stage_add_and_rig_services(self) -> None:
        controller = StudioController()
        controller.new_project(project_id="demo", name="Demo", usd_path="scene.usd")
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary(
                        "/World/Fisheye",
                        "Camera",
                        attributes={"cameraProjectionType": "fisheyePolynomial"},
                    ),
                ]
            )
        )
        ids = {
            item["manifest"]["plugin_id"]
            for item in controller.sensor_plugin_catalog()
        }
        self.assertIn("fisheye_camera", ids)
        sensor = controller.add_sensor_from_stage(
            "fisheye_camera", "/World/Fisheye", "fish"
        )
        self.assertEqual("fisheye_camera", sensor.plugin)
        rig = controller.add_rig("front", ["fish"])
        self.assertEqual("front", rig.rig_id)
        self.assertEqual("front", controller.get_sensor("fish").sync_group_id)
        preview = controller.effective_sensor_preview("fish")
        self.assertIn("parameters", preview)
        capability_rows = controller.preflight_summary()["sensor_capabilities"]
        self.assertEqual("fish", capability_rows[0]["sensor_id"])
        self.assertEqual(
            "instantaneous", capability_rows[0]["capabilities"]["time_model"]
        )


if __name__ == "__main__":
    unittest.main()
