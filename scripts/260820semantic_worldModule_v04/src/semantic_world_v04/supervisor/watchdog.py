"""Pure timeout decisions for Segment Worker monitoring."""

from dataclasses import dataclass

from semantic_world_v04.core.models import ExecutionPolicy, SegmentStatus


@dataclass(frozen=True)
class WatchdogDecision:
    failure_code: str
    message: str


class SegmentWatchdog:
    def __init__(self, policy: ExecutionPolicy, started_monotonic: float) -> None:
        self.policy = policy
        self.started_monotonic = started_monotonic
        self.last_progress_monotonic = started_monotonic
        self.last_committed = 0

    def observe(
        self,
        status: SegmentStatus,
        *,
        now_monotonic: float,
        process_alive: bool,
        heartbeat_age_seconds=None,
    ):
        if not process_alive:
            return None
        if status.capture_groups_current > self.last_committed:
            self.last_committed = status.capture_groups_current
            self.last_progress_monotonic = now_monotonic
        if (
            status.state in {"planned", "queued", "starting"}
            and now_monotonic - self.started_monotonic
            > self.policy.segment_start_timeout_seconds
        ):
            return WatchdogDecision(
                "segment_start_timeout",
                "Segment Worker did not enter running state before timeout",
            )
        if (
            status.state in {"running", "completed", "cancelled", "failed"}
            and heartbeat_age_seconds is not None
            and heartbeat_age_seconds > self.policy.heartbeat_timeout_seconds
        ):
            if status.state == "completed":
                return WatchdogDecision(
                    "segment_exit_timeout",
                    "Completed Segment Worker did not exit before timeout",
                )
            return WatchdogDecision(
                "heartbeat_timeout",
                "Segment Worker heartbeat was not updated before timeout",
            )
        if (
            status.state == "running"
            and now_monotonic - self.last_progress_monotonic
            > self.policy.no_progress_timeout_seconds
        ):
            return WatchdogDecision(
                "no_progress_timeout",
                "Segment Worker produced no new capture group before timeout",
            )
        return None
