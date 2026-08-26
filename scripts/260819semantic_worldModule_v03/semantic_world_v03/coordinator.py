"""Config-driven acquisition coordinator with frame-level commit semantics."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from .config import RunConfig
from .errors import SensorCaptureError
from .ledger import CommitLedger, LedgerRecord
from .models import CaptureRequest, WorldSnapshot
from .rendering import RenderGroupManager
from .sinks import FilesystemSink
from .timing import CaptureTimeline
from .transactions import FrameTransaction


class CaptureCoordinator:
    def __init__(
        self,
        config: RunConfig,
        drivers: dict[str, Any],
        render_groups: RenderGroupManager,
        sink: FilesystemSink,
        ledger: CommitLedger,
        heartbeat: Any | None = None,
    ) -> None:
        self.config = config
        self.drivers = drivers
        self.render_groups = render_groups
        self.sink = sink
        self.ledger = ledger
        self.heartbeat = heartbeat
        self.timeline = CaptureTimeline(config)

    def capture_frame(self, variant_id: str, frame_id: int, snapshot: WorldSnapshot) -> bool:
        if self.ledger.contains(variant_id, frame_id):
            return False
        expected_step = self.timeline.physics_step_for_frame(frame_id)
        if snapshot.physics_step != expected_step:
            raise RuntimeError(
                f"Frame {frame_id} expected physics step {expected_step}, got {snapshot.physics_step}"
            )
        capture_id = f"{self.config.run_id}:{variant_id}:{frame_id:08d}"
        variant = self.config.variant(variant_id)
        requests: list[tuple[Any, CaptureRequest]] = []
        for due in self.timeline.due_for_frame(frame_id):
            spec = self.config.sensor(due.sensor_id)
            group = self.config.render_groups[spec.render_group]
            request = CaptureRequest(
                run_id=self.config.run_id,
                capture_id=capture_id,
                frame_id=frame_id,
                sample_id=due.sample_id,
                sensor_id=spec.sensor_id,
                variant_id=variant_id,
                render_group=spec.render_group,
                snapshot=snapshot,
                requested_modalities=variant.modalities_for(spec),
                rt_subframes=group.rt_subframes,
                interval_start=due.interval_start,
                interval_end=due.interval_end,
            )
            requests.append((self.drivers[spec.sensor_id], request))
        if self.heartbeat:
            self.heartbeat.touch(
                "rendering", variant_id=variant_id, frame_id=frame_id,
                sensor_ids=[request.sensor_id for _, request in requests],
            )
        packets, errors = self.render_groups.acquire_with_errors(requests)
        expected = {request.sensor_id: request for _, request in requests}
        valid_packets = []
        for packet in packets:
            request = expected.get(packet.sensor_id)
            mismatch = (
                request is None
                or packet.capture_id != capture_id
                or packet.frame_id != frame_id
                or packet.variant_id != variant_id
                or packet.physics_step != snapshot.physics_step
                or packet.world_state_hash != snapshot.state_hash
            )
            if mismatch:
                errors[packet.sensor_id] = SensorCaptureError(
                    f"Sensor {packet.sensor_id} returned a packet that does not match its request"
                )
            elif not packet.validation_passed:
                errors[packet.sensor_id] = SensorCaptureError(
                    f"Sensor {packet.sensor_id} validation failed: "
                    + "; ".join(packet.validation_errors)
                )
            else:
                valid_packets.append(packet)
        packets = tuple(valid_packets)
        packets = tuple(
            replace(
                packet,
                payloads={
                    modality: packet.payloads[modality]
                    for modality in variant.modalities_for(
                        self.config.sensor(packet.sensor_id)
                    )
                    if modality in packet.payloads
                },
            )
            for packet in packets
        )
        received = {packet.sensor_id for packet in packets}
        required = {
            request.sensor_id
            for _, request in requests
            if self.config.sensor(request.sensor_id).output.required
        }
        missing = sorted(required - received)
        if missing:
            details = "; ".join(f"{name}: {errors.get(name)!r}" for name in missing)
            raise RuntimeError(f"Required sensors produced no packet: {details}")
        due_ids = {request.sensor_id for _, request in requests}
        for group in self.config.capture.synchronization_groups:
            failed_members = set(group.sensor_ids) & due_ids & set(errors)
            if group.commit_policy == "all_or_nothing" and failed_members:
                raise RuntimeError(
                    f"Synchronization group {group.group_id} failed: "
                    + ", ".join(sorted(failed_members))
                )
        if errors and self.heartbeat:
            self.heartbeat.touch(
                "optional_sensor_failure",
                variant_id=variant_id,
                frame_id=frame_id,
                errors={key: repr(value) for key, value in errors.items()},
            )
        transaction = FrameTransaction(self.config.output, variant_id, frame_id)
        try:
            for packet in packets:
                self.sink.write(transaction, self.config.sensor(packet.sensor_id), packet)
            relative_files = transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        self.ledger.record(
            LedgerRecord(
                run_id=self.config.run_id,
                config_fingerprint=self.config.fingerprint,
                variant_id=variant_id,
                frame_id=frame_id,
                capture_id=capture_id,
                sensor_ids=tuple(sorted(received)),
                relative_files=relative_files,
                committed_unix=time.time(),
            )
        )
        if self.heartbeat:
            self.heartbeat.touch(
                "committed", variant_id=variant_id, frame_id=frame_id,
                sensor_ids=sorted(received),
            )
        return True
