import tempfile
import unittest
from pathlib import Path

from semantic_world_v04.core.errors import SchemaError
from semantic_world_v04.stage import PrimSummary, StageIndex
from semantic_world_v04.studio import RecentProjectStore, StudioController


class StudioV044UxTests(unittest.TestCase):
    def test_new_project_rejects_empty_usd_before_becoming_editable(self):
        controller = StudioController()

        with self.assertRaises(SchemaError):
            controller.new_project(
                project_id="invalid-draft",
                name="Invalid Draft",
                usd_path="",
            )

        self.assertIsNone(controller.project)

    def _controller_with_stage(self) -> StudioController:
        controller = StudioController()
        controller.new_project(
            project_id="ux-demo", name="UX Demo", usd_path="scene.usda"
        )
        controller.set_stage_index(
            StageIndex(
                [
                    PrimSummary("/", "PseudoRoot"),
                    PrimSummary("/World", "Xform"),
                    PrimSummary("/World/KeyLight", "DistantLight"),
                    PrimSummary("/World/Excavator", "Xform"),
                    PrimSummary("/World/Excavator/BoomCamera", "Camera"),
                    PrimSummary(
                        "/World/Fisheye",
                        "Camera",
                        attributes={
                            "omni:lensdistortion:model": "opencvFisheye"
                        },
                        applied_schemas=("OmniLensDistortionOpenCvFisheyeAPI",),
                    ),
                    PrimSummary(
                        "/World/Lidar",
                        "OmniLidar",
                        applied_schemas=("OmniSensorGenericLidarCoreAPI",),
                    ),
                ]
            )
        )
        return controller

    def test_new_projects_default_to_pathtracing_production(self) -> None:
        controller = self._controller_with_stage()
        self.assertEqual("pathtracing_production", controller.current_render_preset_id())
        self.assertEqual("PathTracing", controller.project.render.renderer)
        self.assertEqual(1280, controller.project.render.resolution_width)
        self.assertEqual(64, controller.project.render.total_spp)

    def test_sensor_candidates_prefer_specialized_plugin_and_toggle(self) -> None:
        controller = self._controller_with_stage()
        candidates = {
            item["prim_path"]: item for item in controller.discover_sensor_candidates()
        }
        self.assertEqual(
            "pinhole_camera",
            candidates["/World/Excavator/BoomCamera"]["plugin_id"],
        )
        self.assertEqual("fisheye_camera", candidates["/World/Fisheye"]["plugin_id"])
        self.assertEqual("rtx_lidar", candidates["/World/Lidar"]["plugin_id"])

        sensor = controller.set_stage_sensor_selected(
            "/World/Excavator/BoomCamera", True
        )
        self.assertEqual("boomcamera", sensor.sensor_id)
        controller.set_stage_sensor_selected("/World/Excavator/BoomCamera", False)
        self.assertFalse(sensor.enabled)
        controller.set_stage_sensor_selected("/World/Excavator/BoomCamera", True)
        self.assertTrue(sensor.enabled)
        self.assertEqual(1, len(controller.project.sensors))

    def test_visual_variant_and_flat_modality_matrix(self) -> None:
        controller = self._controller_with_stage()
        sensor = controller.set_stage_sensor_selected(
            "/World/Excavator/BoomCamera", True
        )
        variant = controller.create_isolate_variant(["/World/Excavator"])
        self.assertEqual("excavator_only", variant.variant_id)
        self.assertEqual(["/World/KeyLight"], variant.protected_paths)

        controller.set_binding_enabled(variant.variant_id, sensor.sensor_id, True)
        controller.set_modality_enabled(
            variant.variant_id, sensor.sensor_id, "depth_linear", True
        )
        controller.set_modality_enabled(
            variant.variant_id, sensor.sensor_id, "depth_color", False
        )
        matrix = controller.capture_matrix(sensor.sensor_id)
        row = next(
            item for item in matrix["rows"] if item["variant_id"] == variant.variant_id
        )
        self.assertIn("depth_linear", row["selected_modalities"])
        self.assertNotIn("depth_color", row["selected_modalities"])

        selected = controller.apply_modality_preset(
            variant.variant_id, sensor.sensor_id, "common_all"
        )
        self.assertEqual(
            [
                "rgb",
                "depth_linear",
                "depth_color",
                "semantic_id",
                "semantic_color",
            ],
            selected,
        )
        summary = controller.capture_plan_summary()
        self.assertEqual(2, summary["enabled_bindings"])

        controller.set_binding_enabled(variant.variant_id, sensor.sensor_id, False)
        row = next(
            item
            for item in controller.capture_matrix(sensor.sensor_id)["rows"]
            if item["variant_id"] == variant.variant_id
        )
        self.assertFalse(row["binding_enabled"])
        self.assertEqual([], row["selected_modalities"])

    def test_render_presets_are_detected_and_custom_is_preserved(self) -> None:
        controller = self._controller_with_stage()
        controller.apply_render_preset("realtime_preview")
        self.assertEqual("realtime_preview", controller.current_render_preset_id())
        controller.project.render.resolution_width = 777
        self.assertEqual("custom", controller.current_render_preset_id())

    def test_recent_project_store_is_deduplicated_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = RecentProjectStore(root / "recent.json", limit=2)
            first = root / "first.swproject"
            second = root / "second.swproject"
            first.mkdir()
            second.mkdir()
            store.record(first, project_id="first")
            store.record(second, project_id="second")
            store.record(first, project_id="first-new")
            rows = store.list(existing_only=True)
            self.assertEqual(2, len(rows))
            self.assertEqual(str(first.resolve()), rows[0]["path"])
            self.assertEqual("first-new", rows[0]["project_id"])


if __name__ == "__main__":
    unittest.main()
