"""Portable capture identity and owned-data readiness, independent of Isaac."""
from dataclasses import dataclass, field
import time
import uuid
import math


class SampleError(RuntimeError):
    def __init__(self, reason, message, sensor_id=None):
        self.reason, self.sensor_id = reason, sensor_id
        super().__init__(message)


@dataclass
class CaptureTicket:
    run_id: str
    capture_id: str
    group_id: int
    stage_generation: str
    expected_sim_ns: int
    pose_revision: int
    expected: frozenset
    timeout_s: float
    attempt_id: int = 0
    request_id: str = field(default_factory=lambda:uuid.uuid4().hex)
    received: dict = field(default_factory=dict)
    validated: set = field(default_factory=set)
    errors: dict = field(default_factory=dict)
    open: bool = True
    submitted: bool = False
    render_complete: bool = False
    started_ns: int = field(default_factory=time.monotonic_ns)

    @property
    def pending(self): return sorted(self.expected-self.validated)
    @property
    def complete(self): return self.render_complete and not self.pending and not self.errors
    @property
    def expired(self): return time.monotonic_ns()-self.started_ns > self.timeout_s*1e9
    def identity(self):
        return {k:getattr(self,k) for k in ('run_id','capture_id','group_id','stage_generation','request_id','attempt_id')}

    def receive(self, sensor, payload, generation, request_id):
        if not self.open: raise SampleError('callback_rejected_window_closed','Closed request',sensor)
        if generation!=self.stage_generation or request_id!=self.request_id:
            raise SampleError('callback_wrong_request','Wrong request or stage generation',sensor)
        if not self.submitted or sensor not in self.expected:
            raise SampleError('callback_wrong_request','Unscheduled sensor',sensor)
        if sensor in self.received: return False
        self.received[sensor]=payload
        return True

    def validate(self, sensor, source_ns, pose_error, evidence, source_frame_id=None, previous_frame_id=None):
        if sensor not in self.received: raise SampleError('callback_missing','Payload missing',sensor)
        if abs(source_ns-self.expected_sim_ns)>2:
            raise SampleError('source_time_mismatch',f'{source_ns} != {self.expected_sim_ns}',sensor)
        if not math.isfinite(pose_error) or pose_error>2e-3:
            raise SampleError('render_pose_mismatch',f'Pose max matrix difference {pose_error}',sensor)
        if source_frame_id is not None and previous_frame_id is not None and source_frame_id==previous_frame_id:
            raise SampleError('source_frame_stale','Repeated source frame',sensor)
        if evidence not in ('serialized_manual_writer','completed_render_poll'):
            raise SampleError('source_frame_unknown','No freshness evidence',sensor)
        self.validated.add(sensor)

    def close(self): self.open=False
