"""One native physics-step clock; wall time is only a performance measurement."""
import math

LEGACY_TIME_BASE = 'prescribed_control_simulation_seconds'
NATIVE_TIME_BASE = 'native_simulation_seconds'
TIME_BASES = {LEGACY_TIME_BASE: 1, NATIVE_TIME_BASE: 2}


def validate_time_base(metadata):
    basis = metadata.get('time_base', LEGACY_TIME_BASE)
    if basis not in TIME_BASES:
        raise ValueError('Unsupported trajectory time_base: ' + str(basis))
    if metadata.get('time_basis_version', TIME_BASES[basis]) != TIME_BASES[basis]:
        raise ValueError('Trajectory time basis version mismatch')
    return basis


class NativeStepClock:
    def __init__(self):
        self.generation = 0
        self.bind(0.)

    def bind(self, native_time):
        native_time = float(native_time)
        if not math.isfinite(native_time) or native_time < 0:
            raise ValueError('Invalid native clock origin')
        self.origin = self.last = native_time
        self.step_index = 0
        self.elapsed = 0.
        self.generation += 1

    def advance(self, native_time, step_dt):
        native_time, step_dt = float(native_time), float(step_dt)
        if not math.isfinite(native_time) or not math.isfinite(step_dt) or step_dt <= 0:
            raise ValueError('Invalid native physics step')
        delta = native_time-self.last
        if delta < -1e-8:
            raise RuntimeError('Native simulation time moved backwards; recording cannot continue')
        if abs(delta) <= 1e-10:
            return 0.  # Never advance twice for the same native step.
        if abs(delta-step_dt) > max(1e-6, step_dt*1e-4):
            raise RuntimeError('Native physics step gap; recording cannot silently skip steps')
        self.last = native_time
        self.elapsed = max(0., native_time-self.origin)
        self.step_index += 1
        return delta
