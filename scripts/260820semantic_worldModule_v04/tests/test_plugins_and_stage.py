import unittest

from semantic_world_v04.core.models import SensorDefinition, VariantDefinition
from semantic_world_v04.plugins import PluginRegistry, build_default_registry
from semantic_world_v04.plugins.sensors import PinholeCameraPlugin
from semantic_world_v04.plugins.variants import IncludePathsVariant
from semantic_world_v04.stage import PrimSummary, StageIndex
from semantic_world_v04.stage.omni_adapter import _jsonable


def make_stage() -> StageIndex:
    return StageIndex(
        [
            PrimSummary("/", "PseudoRoot"),
            PrimSummary("/World", "Xform"),
            PrimSummary("/World/Environment", "Xform"),
            PrimSummary("/World/Environment/Ground", "Mesh"),
            PrimSummary("/World/Excavator", "Xform"),
            PrimSummary("/World/Excavator/Body", "Mesh"),
            PrimSummary(
                "/World/Excavator/Camera",
                "Camera",
                attributes={
                    "focalLength": 24.0,
                    "horizontalAperture": 20.955,
                    "clippingRange": [0.1, 10000.0],
                },
            ),
            PrimSummary("/World/Light", "DistantLight"),
            PrimSummary("/World/Other", "Xform"),
            PrimSummary("/World/Other/Mesh", "Mesh"),
        ],
        stage_identifier="scene.usda",
    )


class PluginAndStageTests(unittest.TestCase):
    def test_matrix_like_usd_values_are_serialized_as_numeric_rows(self) -> None:
        class FakeMatrix:
            def GetRow(self, index):
                return (index * 4, index * 4 + 1, index * 4 + 2, index * 4 + 3)

        self.assertEqual(
            [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15]],
            _jsonable(FakeMatrix()),
        )

    def test_camera_parameters_are_read_from_stage(self) -> None:
        stage = make_stage()
        plugin = PinholeCameraPlugin()
        prim = stage.require("/World/Excavator/Camera")
        sensor = plugin.definition_from_prim("boom_camera", prim)
        self.assertEqual(24.0, sensor.parameters["focalLength"])
        self.assertEqual(24.0, sensor.stage_parameters["focalLength"])
        self.assertEqual("stage", sensor.parameter_sources["focalLength"])

        sensor.parameters["focalLength"] = 35.0
        sensor.parameter_sources["focalLength"] = "override"
        payload = plugin.compile_runtime_payload(sensor, stage)
        self.assertEqual(35.0, payload["parameters"]["focalLength"])
        self.assertEqual(24.0, payload["stage_parameters"]["focalLength"])
        self.assertEqual("override", payload["parameter_sources"]["focalLength"])

    def test_only_explicit_camera_overrides_are_authored_to_usd(self) -> None:
        plugin = PinholeCameraPlugin()
        sensor = SensorDefinition(
            sensor_id="camera",
            plugin="pinhole_camera",
            prim_path="/World/Camera",
            parameters={
                "focalLength": 35.0,
                "horizontalAperture": 20.0,
                "resolution": [1280, 720],
            },
            parameter_sources={
                "focalLength": "override",
                "horizontalAperture": "stage",
                "resolution": "override",
            },
        )
        self.assertEqual(
            {"focalLength": 35.0}, plugin.runtime_override_parameters(sensor)
        )

    def test_include_paths_keeps_sensor_ancestors_and_subtree(self) -> None:
        stage = make_stage()
        variant = VariantDefinition(
            variant_id="isolated",
            strategy="include_paths",
            include_paths=["/World/Excavator"],
            protected_paths=["/World/Light"],
        )
        plan = IncludePathsVariant().visibility_plan(
            variant, stage, ["/World/Excavator/Camera"]
        )
        self.assertIn("/World/Environment", plan.hidden_roots)
        self.assertIn("/World/Other", plan.hidden_roots)
        self.assertNotIn("/World/Excavator", plan.hidden_roots)
        self.assertNotIn("/World/Light", plan.hidden_roots)

    def test_registry_rejects_duplicate_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register_sensor(PinholeCameraPlugin())
        with self.assertRaisesRegex(Exception, "duplicate"):
            registry.register_sensor(PinholeCameraPlugin())

    def test_default_registry_contains_mvp_plugins(self) -> None:
        registry = build_default_registry()
        self.assertEqual(
            ["fisheye_camera", "pinhole_camera", "rtx_lidar"],
            registry.sensor_ids(),
        )
        self.assertEqual(["full_scene", "include_paths"], registry.variant_ids())
        self.assertEqual(
            {
                "depth_color",
                "depth_linear",
                "instance_color",
                "instance_id",
                "point_cloud",
                "point_cloud_ply",
                "rgb",
                "semantic_color",
                "semantic_id",
                "surface_normal",
                "surface_normal_color",
            },
            set(registry.modality_ids()),
        )


if __name__ == "__main__":
    unittest.main()
