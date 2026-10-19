"""Joint commands in degrees and simulation seconds; no Isaac/ROS dependencies."""
from dataclasses import dataclass
import math

MODES = ("direct", "target", "periodic")
# Tensor limits use float32 radians; tolerate only their degree conversion roundoff.
ANGLE_EPSILON_DEG = 1e-4
PHYSX_REVOLUTE_MAX_DEG = math.degrees(2*math.pi-1e-5)

def physx_revolute_limits(lower,upper):
    """Unbounded USD limits do not remove PhysX's reduced-coordinate target bound."""
    return max(float(lower),-PHYSX_REVOLUTE_MAX_DEG),min(float(upper),PHYSX_REVOLUTE_MAX_DEG)

def bounded_keyboard_angle(angle,delta,lower,upper):
    """An initial pose outside a configured interval moves inward without teleporting."""
    if angle<lower:return min(upper,angle+max(0,delta))
    if angle>upper:return max(lower,angle+min(0,delta))
    return max(lower,min(upper,angle+delta))


def finite(value, label):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


@dataclass
class JointState:
    initial: float
    minimum: float
    maximum: float
    angle: float
    target: float
    lower: float
    upper: float
    speed: float
    mode: str = "direct"
    running: bool = False
    direction: int = 1


class JointController:
    def __init__(self, initial, limits, speeds):
        self.states = {}
        for name, angle in initial.items():
            lo, hi = limits[name]
            if math.isnan(lo) or math.isnan(hi) or lo > hi:
                raise ValueError(f"{name}: invalid articulation limits")
            self.states[name] = JointState(angle, lo, hi, angle, angle,
                max(lo, angle - 15.0), min(hi, angle + 15.0), speeds[name])

    def hold(self, names, actual):
        for name in names:
            state = self.states[name]
            state.angle = float(actual[name])
            state.running = False

    def select_mode(self, name, mode, actual):
        if mode not in MODES:
            raise ValueError(f"Unknown joint mode: {mode}")
        self.hold([name], actual)
        self.states[name].mode = mode

    def execute(self, commands, actual):
        """Validate the whole batch before changing any joint. Drafts are not commands."""
        prepared = {}
        for name, command in commands.items():
            state = self.states[name]
            mode = command["mode"]
            if mode not in MODES:
                raise ValueError(f"{name}: unknown mode {mode}")
            values = {"angle": finite(actual[name], f"{name} actual angle")}
            fields = ("lower", "upper", "speed") if mode == "periodic" else (
                ("target", "speed") if mode == "target" else ("target",))
            for field in fields:
                value = finite(command[field], f"{name} {field}")
                if field == "speed":
                    if value <= 0:
                        raise ValueError(f"{name}: speed must be positive (deg/s)")
                else:
                    if value < state.minimum - ANGLE_EPSILON_DEG or value > state.maximum + ANGLE_EPSILON_DEG:
                        raise ValueError(f"{name}: {field} must be within [{state.minimum:g}, {state.maximum:g}] deg")
                    value = min(state.maximum, max(state.minimum, value))
                values[field] = value
            if mode == "periodic" and values["lower"] >= values["upper"]:
                raise ValueError(f"{name}: lower must be less than upper")
            prepared[name] = (mode, values)
        for name, (mode, values) in prepared.items():
            state = self.states[name]
            state.mode = mode
            for field, value in values.items():
                setattr(state, field, value)
            state.running = mode != "direct"
            state.direction = -1 if state.angle >= state.upper else 1
            if mode == "direct":
                state.angle = state.target

    def step(self, dt):
        dt = finite(dt, "Simulation delta")
        if dt < 0:
            raise ValueError("Simulation delta cannot be negative")
        for state in self.states.values():
            if not state.running or dt == 0:
                continue
            distance = state.speed * dt
            if state.mode == "target":
                error = state.target - state.angle
                if abs(error) <= distance:
                    state.angle, state.running = state.target, False
                else:
                    state.angle += math.copysign(distance, error)
            elif state.mode == "periodic":
                # Enter a new interval at the requested speed, without teleporting.
                if state.angle < state.lower:
                    gap = state.lower - state.angle
                    state.angle += min(distance, gap)
                    distance = max(0.0, distance - gap)
                    state.direction = 1
                elif state.angle > state.upper:
                    gap = state.angle - state.upper
                    state.angle -= min(distance, gap)
                    distance = max(0.0, distance - gap)
                    state.direction = -1
                if distance > 0:
                    width = state.upper - state.lower
                    offset = state.angle - state.lower
                    phase = offset if state.direction > 0 else 2 * width - offset
                    phase = (phase + distance) % (2 * width)
                    state.angle = state.lower + (phase if phase < width else 2 * width - phase)
                    state.direction = 1 if phase < width else -1
        return {name: state.angle for name, state in self.states.items()}

    def reset(self):
        for state in self.states.values():
            state.angle = state.initial
            state.running = False
            state.direction = 1
