"""Main-loop slow motion; simulation dt and wall-clock pacing stay separate."""
import math
import time
from .performance import timed


def pacing_config(config):
    values = dict(config.get("simulation_pacing", {}))
    hz = float(values.get("simulation_hz", 60))
    cap = float(values.get("max_real_time_factor", 0.1))
    if not math.isfinite(hz) or hz <= 0 or not hz.is_integer():
        raise ValueError("simulation_hz must be positive.")
    if not math.isfinite(cap) or not 0 < cap <= 0.1:
        raise ValueError("max_real_time_factor must be in (0, 0.1].")
    fps = math.floor(hz * cap + 1e-9)
    if fps < 1:
        raise ValueError("The configured main-loop cap must be at least 1 FPS.")
    return {"simulation_hz": hz, "max_real_time_factor": cap, "main_loop_fps": fps}


class WallPacer:
    """No catch-up credit: every new step waits relative to the preceding step."""
    def __init__(self, interval, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.previous = None

    def reset(self):
        self.previous = self.clock()

    def wait(self):
        if self.previous is None:
            self.reset()
        remaining = self.previous + self.interval - self.clock()
        while remaining > 0:
            self.sleep(remaining)
            remaining = self.previous + self.interval - self.clock()
        self.previous = self.clock()


class SimulationPacing:
    LOOP = "/app/runLoops/main/"
    FIXED = {
        "/app/player/useFixedTimeStepping": True,
        "/app/player/useFastMode": True,
        "/app/player/CompensatePlayDelayInSecs": 0.0,
        "/app/player/timelineSubsampleRate": 1,
        LOOP + "manualModeEnabled": True,
    }

    def __init__(self, app, timeline, stage, layer, config):
        import carb.settings
        from pxr import PhysxSchema, Usd, UsdPhysics
        self.app, self.timeline = app, timeline
        self.settings = carb.settings.get_settings()
        self.config = pacing_config(config)
        self.dt = 1.0 / self.config["simulation_hz"]
        self.fixed = dict(self.FIXED, **{self.LOOP + "manualStepSize": self.dt})
        self.original = {p: self.settings.get(p) for p in
                         [*self.fixed, self.LOOP + "rateLimitEnabled", self.LOOP + "rateLimitFrequency"]}
        self.active = self.closed = False
        self.actual_rtf = None
        self.sample = None
        # A 1 ms margin keeps the measured completed-frame rate below the cap
        # despite small differences in frame callback/render completion timing.
        self.wall_pacer = WallPacer(max(self.dt / self.config["max_real_time_factor"],
                                       1.0 / self.config["main_loop_fps"]) + 0.001)
        # These are temporary opinions in the project's anonymous session layer.
        layer.timeCodesPerSecond = self.config["simulation_hz"]
        with Usd.EditContext(stage, layer):
            for prim in stage.Traverse():
                if prim.IsA(UsdPhysics.Scene):
                    PhysxSchema.PhysxSceneAPI.Apply(prim).CreateTimeStepsPerSecondAttr().Set(
                        int(self.config["simulation_hz"]))
        self.subscription = app.get_pre_update_event_stream().create_subscription_to_pop(
            self._pre_update, name="LiDAR main-loop pacing")

    def _set(self, path, value):
        if self.settings.get(path) != value:
            self.settings.set(path, value)

    def _restore(self, paths):
        for path in paths:
            value = self.original[path]
            if value is None:
                self.settings.destroy_item(path)
            else:
                self.settings.set(path, value)

    def play(self):
        if self.closed:
            return
        if not self.active:
            self.active = True
            self.wall_pacer.reset()
            self.sample = (time.monotonic(), self.timeline.get_current_time())
            self.actual_rtf = None
        self._apply()

    def _apply(self):
        for path, value in self.fixed.items():
            self._set(path, value)
        self._set(self.LOOP + "rateLimitEnabled", True)
        self._set(self.LOOP + "rateLimitFrequency", self.config["main_loop_fps"])

    def pause(self):
        if self.active:
            self.active = False
            self.sample = None
            self.actual_rtf = None
            self._restore([self.LOOP + "rateLimitEnabled", self.LOOP + "rateLimitFrequency"])

    @timed('pacing.pre_update_including_wait')
    def _pre_update(self, _event):
        if self.closed:
            return
        if not self.timeline.is_playing():
            self.pause()
            return
        self.play()
        # The native limiter is primary. This enforces minimum spacing even if
        # Play replaces its setting or a delayed frame would otherwise catch up.
        if getattr(self, 'performance', None):
            with self.performance.span('pacing.wait'): self.wall_pacer.wait()
        else:
            self.wall_pacer.wait()

    def update(self, simulation_time):
        if not self.active or not self.timeline.is_playing():
            return
        now = time.monotonic()
        if self.sample is None or simulation_time < self.sample[1]:
            self.sample = (now, simulation_time)
        elif now - self.sample[0] >= 2:
            self.actual_rtf = (simulation_time - self.sample[1]) / (now - self.sample[0])
            self.sample = (now, simulation_time)

    def metadata(self):
        return dict(self.config, simulation_step_s=self.dt, actual_rtf=self.actual_rtf,
                    policy="fixed_step_no_catch_up", clock="simulation")

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.subscription = None
        self._restore(self.original)
