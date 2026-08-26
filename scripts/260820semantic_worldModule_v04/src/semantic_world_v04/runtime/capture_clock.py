"""Configure Replicator scheduling from sensor time-model requirements."""

from typing import Any, Iterable


class SensorCaptureClock:
    """Own the global Replicator capture-on-play switch for one Runtime.

    Frame sensors are sampled explicitly at capture boundaries.  Scan-window
    sensors such as a rotary RTX LiDAR must instead receive every timeline tick
    so their internal history exists when the boundary is reached.  Keeping the
    global switch here prevents individual plugins from silently changing the
    scheduling semantics of all other sensors.
    """

    def __init__(self) -> None:
        self.continuous_history_enabled = False

    def configure(self, drivers: Iterable[Any]) -> bool:
        self.continuous_history_enabled = any(
            bool(getattr(driver, "requires_continuous_history", False))
            for driver in drivers
        )
        import omni.replicator.core as rep  # type: ignore

        rep.orchestrator.set_capture_on_play(self.continuous_history_enabled)
        return self.continuous_history_enabled

    def close(self) -> None:
        try:
            import omni.replicator.core as rep  # type: ignore

            rep.orchestrator.set_capture_on_play(False)
        except Exception:
            pass
        self.continuous_history_enabled = False
