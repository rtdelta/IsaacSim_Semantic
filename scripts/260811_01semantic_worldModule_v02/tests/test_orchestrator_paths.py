"""Tests for the single-config command-line boundary."""

from __future__ import annotations

import unittest
from itertools import count
from pathlib import Path
import tempfile
from types import SimpleNamespace

from capture_launch_config import CaptureLaunchConfig
from capture_context import (
    CaptureContext,
    CaptureOperation,
    CaptureReceipt,
    CaptureVariant,
    ProbeReceipt,
)
from capture_timing import CaptureTiming
from isolated_render_config import IsolatedRenderConfig
from joint_control_profile import JointControlProfile
from render_profile import RenderProfile
from simulation_orchestrator import (
    RUN_CONFIG_SCHEMA_VERSION,
    VariantSettleError,
    base_manifest,
    capture_variant_to_staging,
    parse_args,
    resolve_renderer_selection,
    settle_variant,
    update_source_stage_integrity,
)
from stage_preflight import file_record


class FakeWorldScheduler:
    def __init__(self) -> None:
        self.assertions = 0

    def assert_still_frozen(self, _snapshot: object) -> None:
        self.assertions += 1


class FakeVariantController:
    def __init__(self) -> None:
        self.current_variant = CaptureVariant.FULL_SCENE
        self.visibility_generation = 0
        self.force_reapply_count = 0

    def transition_to(self, target: CaptureVariant) -> SimpleNamespace:
        if target is not self.current_variant:
            self.current_variant = target
            self.visibility_generation += 1
        return SimpleNamespace(
            variant=target,
            visibility_generation=self.visibility_generation,
        )

    def force_reapply(self, target: CaptureVariant) -> SimpleNamespace:
        self.current_variant = target
        self.visibility_generation += 1
        self.force_reapply_count += 1
        return SimpleNamespace(
            variant=target,
            visibility_generation=self.visibility_generation,
        )

    def assert_state(
        self,
        target: CaptureVariant,
        *,
        expected_generation: int | None = None,
    ) -> SimpleNamespace:
        if self.current_variant is not target:
            raise RuntimeError("wrong variant")
        if (
            expected_generation is not None
            and expected_generation != self.visibility_generation
        ):
            raise RuntimeError("wrong generation")
        return SimpleNamespace(variant=target)


class FakeCameraScheduler:
    def __init__(self, probe_results: list[bool] | None = None) -> None:
        self.transform = tuple(float(index) for index in range(16))
        self.probe_results = list(probe_results or [True])
        self.probe_contexts: list[CaptureContext] = []
        self.reset_count = 0
        self.reconnect_count = 0

    def get_state(self) -> dict[str, object]:
        return {"world_transform": list(self.transform)}

    def reset_render_history(self) -> None:
        self.reset_count += 1

    def reconnect_annotators(self) -> None:
        self.reconnect_count += 1

    def probe(self, context: CaptureContext, *, rt_subframes: int) -> ProbeReceipt:
        self.probe_contexts.append(context)
        passed = self.probe_results.pop(0)
        return ProbeReceipt(
            frame_id=context.frame_id,
            variant=context.variant,
            visibility_generation=context.visibility_generation,
            attempt=context.attempt,
            probe_index=context.probe_index,
            resolution=(1280, 720),
            semantic_labels_present=("target",) if passed else ("stale",),
            semantic_dataset_ids_present=(1,),
            validation_passed=passed,
            validation_errors=() if passed else ("stale variant",),
        )

    def capture(self, context: CaptureContext) -> CaptureReceipt:
        return CaptureReceipt(
            frame_id=context.frame_id,
            rgb_path="rgb.png",
            semantic_id_path="semantic.npy",
            semantic_color_path="semantic.png",
            runtime_id_path=None,
            metadata_path="frame.json",
            variant=context.variant,
            visibility_generation=context.visibility_generation,
            settle_attempts_before_capture=(
                context.settle_attempts_before_capture
            ),
        )


def frame_context() -> CaptureContext:
    return CaptureContext(
        frame_id=4,
        dataset_time=0.4,
        timeline_time=0.4,
        physics_step=24,
        camera_path="/World/Camera",
        camera_world_transform=tuple(float(index) for index in range(16)),
        motion_state={},
    )


class OrchestratorPathTests(unittest.TestCase):
    def test_config_is_the_only_business_option(self) -> None:
        args = parse_args(["--config", "configs/capture.json"])
        self.assertEqual(args.config, "configs/capture.json")
        self.assertEqual(vars(args), {"config": "configs/capture.json"})

    def test_config_is_required(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args([])

    def test_legacy_business_option_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--config",
                    "configs/capture.json",
                    "--camera_prim_path",
                    "/root/Camera",
                ]
            )

    def test_unknown_kit_option_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--config", "configs/capture.json", "--/app/window/width=1280"])

    def test_explicit_renderer_must_match_profile(self) -> None:
        profile = RenderProfile.load(
            "configs/render_pathtracing_720p_64spp.json"
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            resolve_renderer_selection("RealTimePathTracing", profile)

    def test_manifest_records_source_and_effective_configuration(self) -> None:
        config = CaptureLaunchConfig.load("configs/capture_motion_camera02.json")
        isolated_render_config = IsolatedRenderConfig.load(
            config.excavator_only_capture.render_prim_paths_config
        )
        profile = RenderProfile.load(config.render_profile).with_capture_overrides(
            rt_subframes=config.rt_subframes,
            warmup_render_frames=config.warmup_render_frames,
        )
        joint_profile = JointControlProfile.load(config.joint_profile)
        timing = CaptureTiming(
            physics_hz=config.physics_hz,
            capture_fps=config.capture_fps,
            capture_initial_frame=config.capture_initial_frame,
            static=config.capture_mode == "static",
        )

        manifest = base_manifest(
            config,
            isolated_render_config,
            None,
            profile,
            joint_profile,
            trajectory_metadata=None,
            timing=timing,
            output_path=Path(config.output),
            original_argv=["simulation_orchestrator.py", "--config", str(config.source_path)],
        )

        self.assertEqual(manifest["schema_version"], RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(
            manifest["launch_config"]["source"]["path"],
            str(config.source_path),
        )
        self.assertEqual(
            manifest["effective_config"]["camera_prim_path"],
            config.camera_prim_path,
        )
        self.assertEqual(
            manifest["effective_config"]["rt_subframes"],
            profile.rt_subframes,
        )
        self.assertTrue(manifest["excavator_only_capture"]["enabled"])
        self.assertEqual(
            manifest["image_output_folders"]["excavator_only_semantic"],
            "excavator_only_semantic",
        )
        self.assertFalse(manifest["front_teeth_only_capture"]["enabled"])
        self.assertEqual(
            manifest["image_output_folders"]["front_teeth_only_semantic"],
            "front_teeth_only_semantic",
        )

    def test_settle_variant_retries_without_advancing_frame_identity(self) -> None:
        camera = FakeCameraScheduler([False, True])
        world = FakeWorldScheduler()
        controller = FakeVariantController()

        report, probes = settle_variant(
            camera_scheduler=camera,
            world_scheduler=world,
            frozen_world=object(),
            variant_controller=controller,
            base_context=frame_context(),
            target_variant=CaptureVariant.FRONT_TEETH_ONLY,
            settle_render_count=1,
            settle_rt_subframes=16,
            maximum_settle_attempts=3,
            probe_sequence=count(),
        )

        self.assertEqual(report.variant, CaptureVariant.FRONT_TEETH_ONLY)
        self.assertEqual(controller.visibility_generation, 2)
        self.assertEqual(controller.force_reapply_count, 1)
        self.assertEqual([probe.validation_passed for probe in probes], [False, True])
        self.assertEqual(camera.reset_count, 2)
        self.assertEqual(
            [context.operation for context in camera.probe_contexts],
            [CaptureOperation.PROBE, CaptureOperation.PROBE],
        )
        self.assertEqual(
            [context.probe_index for context in camera.probe_contexts],
            [0, 1],
        )
        self.assertEqual(
            [context.visibility_generation for context in camera.probe_contexts],
            [1, 2],
        )
        self.assertEqual(camera.reconnect_count, 0)

    def test_settle_variant_raises_after_configured_attempts(self) -> None:
        camera = FakeCameraScheduler([False, False])
        controller = FakeVariantController()
        with self.assertRaisesRegex(VariantSettleError, "did not settle"):
            settle_variant(
                camera_scheduler=camera,
                world_scheduler=FakeWorldScheduler(),
                frozen_world=object(),
                variant_controller=controller,
                base_context=frame_context(),
                target_variant=CaptureVariant.EXCAVATOR_ONLY,
                settle_render_count=1,
                settle_rt_subframes=8,
                maximum_settle_attempts=2,
                probe_sequence=count(),
            )
        self.assertEqual(controller.force_reapply_count, 1)
        self.assertEqual(camera.reconnect_count, 1)

    def test_final_attempt_reapplies_layer_and_reconnects_annotators(self) -> None:
        camera = FakeCameraScheduler([False, False, True])
        controller = FakeVariantController()

        _report, probes = settle_variant(
            camera_scheduler=camera,
            world_scheduler=FakeWorldScheduler(),
            frozen_world=object(),
            variant_controller=controller,
            base_context=frame_context(),
            target_variant=CaptureVariant.FRONT_TEETH_ONLY,
            settle_render_count=1,
            settle_rt_subframes=16,
            maximum_settle_attempts=3,
            probe_sequence=count(),
        )

        self.assertEqual([probe.validation_passed for probe in probes], [False, False, True])
        self.assertEqual(controller.force_reapply_count, 2)
        self.assertEqual(controller.visibility_generation, 3)
        self.assertEqual(camera.reconnect_count, 1)

    def test_source_stage_integrity_detects_content_or_metadata_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "scene.usda"
            source.write_text("#usda 1.0\n", encoding="utf-8")
            manifest = {"inputs": {"source_stage": file_record(source)}}

            first = update_source_stage_integrity(manifest, source)
            self.assertTrue(first["unchanged"])

            source.write_text("#usda 1.0\n# changed\n", encoding="utf-8")
            second = update_source_stage_integrity(manifest, source)
            self.assertFalse(second["unchanged"])

    def test_formal_capture_uses_current_visibility_generation(self) -> None:
        camera = FakeCameraScheduler()
        world = FakeWorldScheduler()
        controller = FakeVariantController()
        controller.transition_to(CaptureVariant.EXCAVATOR_ONLY)

        receipt = capture_variant_to_staging(
            camera_scheduler=camera,
            world_scheduler=world,
            frozen_world=object(),
            variant_controller=controller,
            base_context=frame_context(),
            variant=CaptureVariant.EXCAVATOR_ONLY,
            settle_attempts_before_capture=1,
        )

        self.assertEqual(receipt.visibility_generation, 1)
        self.assertEqual(receipt.variant, CaptureVariant.EXCAVATOR_ONLY)


if __name__ == "__main__":
    unittest.main()
