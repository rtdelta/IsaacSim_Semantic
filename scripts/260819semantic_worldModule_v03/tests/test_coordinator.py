from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from conftest import config_payload, write_config
from semantic_world_v03.config import load_run_config
from semantic_world_v03.coordinator import CaptureCoordinator
from semantic_world_v03.ledger import CommitLedger
from semantic_world_v03.models import (
    AcquisitionKind,
    SensorCapabilities,
    SensorPacket,
    WorldSnapshot,
)
from semantic_world_v03.rendering import RenderGroupManager
from semantic_world_v03.sinks import FilesystemSink


class Backend:
    def __init__(self):
        self.calls = 0

    def render(self, *, rt_subframes):
        self.calls += 1


class SuccessDriver:
    capabilities = SensorCapabilities(AcquisitionKind.SNAPSHOT, ("rgb",), True)

    def __init__(self, sensor_type="camera.pinhole"):
        self.sensor_type = sensor_type

    def read(self, request):
        return SensorPacket(
            run_id=request.run_id,
            capture_id=request.capture_id,
            frame_id=request.frame_id,
            sample_id=request.sample_id,
            sensor_id=request.sensor_id,
            sensor_type=self.sensor_type,
            variant_id=request.variant_id,
            acquisition=AcquisitionKind.SNAPSHOT,
            timestamp=request.snapshot.dataset_time,
            physics_step=request.snapshot.physics_step,
            world_state_hash=request.snapshot.state_hash,
            calibration_hash="calibration",
            payloads={"rgb": b"fake-image"},
        )

    def mark_sample_captured(self):
        pass


class FailingDriver(SuccessDriver):
    def read(self, request):
        raise RuntimeError("optional sensor unavailable")


class MultiModalDriver(SuccessDriver):
    capabilities = SensorCapabilities(
        AcquisitionKind.SNAPSHOT, ("rgb", "semantic_segmentation"), True
    )

    def __init__(self):
        super().__init__()
        self.requested_modalities = None

    def read(self, request):
        self.requested_modalities = request.requested_modalities
        packet = super().read(request)
        return SensorPacket(
            **{
                **packet.__dict__,
                "payloads": {
                    "rgb": b"rgb-must-not-be-written",
                    "semantic_segmentation": b"semantic-id",
                },
            }
        )


class CoordinatorTests(unittest.TestCase):
    def test_optional_sensor_failure_still_commits_required_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = config_payload(root / "output")
            optional = dict(payload["sensors"][0])
            optional["id"] = "optional"
            optional["source"] = {
                "mode": "existing_prim", "prim_path": "/World/Optional"
            }
            optional["output"] = {"sink": "filesystem", "required": False}
            payload["sensors"].append(optional)
            config = load_run_config(write_config(root, payload))
            ledger = CommitLedger(
                config.output, run_id=config.run_id, fingerprint=config.fingerprint
            )
            backend = Backend()
            groups = RenderGroupManager(backend, config.render_groups)
            coordinator = CaptureCoordinator(
                config,
                {"front": SuccessDriver(), "optional": FailingDriver()},
                groups,
                FilesystemSink(),
                ledger,
            )
            snapshot = WorldSnapshot(0, 0.0, 0.0)
            self.assertTrue(coordinator.capture_frame("full_scene", 0, snapshot))
            self.assertFalse(coordinator.capture_frame("full_scene", 0, snapshot))
            self.assertEqual(backend.calls, 1)
            self.assertTrue(ledger.contains("full_scene", 0))
            self.assertEqual(
                (Path(config.output) / "sensors/front/full_scene/frame_00000000/rgb.bin").read_bytes(),
                b"fake-image",
            )

    def test_variant_requests_and_writes_only_selected_modalities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = config_payload(root / "output")
            payload["sensors"][0]["modalities"] = ["rgb", "semantic_segmentation"]
            payload["capture"]["variants"] = [
                {
                    "id": "excavator_only",
                    "visibility": {},
                    "include_paths": ["/World/Excavator"],
                    "modalities_by_sensor": {"front": ["semantic_segmentation"]},
                }
            ]
            config = load_run_config(write_config(root, payload))
            ledger = CommitLedger(
                config.output, run_id=config.run_id, fingerprint=config.fingerprint
            )
            driver = MultiModalDriver()
            coordinator = CaptureCoordinator(
                config,
                {"front": driver},
                RenderGroupManager(Backend(), config.render_groups),
                FilesystemSink(),
                ledger,
            )
            self.assertTrue(
                coordinator.capture_frame(
                    "excavator_only", 0, WorldSnapshot(0, 0.0, 0.0)
                )
            )
            folder = (
                Path(config.output)
                / "sensors/front/excavator_only/frame_00000000"
            )
            self.assertEqual(driver.requested_modalities, ("semantic_segmentation",))
            self.assertTrue((folder / "semantic_segmentation.bin").exists())
            self.assertFalse((folder / "rgb.bin").exists())


if __name__ == "__main__":
    unittest.main()
