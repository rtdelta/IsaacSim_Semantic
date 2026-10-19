"""Prescribed XYZ/yaw pose with independent pitch/roll offset controllers."""
from dataclasses import asdict
import math
from .joint_control import JointController


def finite(*values):
    values = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Motion values must be finite')
    return values


def multiply_wxyz(a, b):
    w, x, y, z = a
    W, X, Y, Z = b
    return (w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y,
            w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W)


class BaseController:
    def __init__(self, position, orientation_wxyz, heading):
        self.initial = (*finite(*position), float(heading))
        q = finite(*orientation_wxyz)
        norm = math.sqrt(sum(v*v for v in q))
        if len(q) != 4 or norm < 1e-12:
            raise ValueError('Initial orientation must be a nonzero quaternion')
        self.initial_orientation = tuple(v/norm for v in q)
        w, x, y, z = self.initial_orientation
        self.initial_pitch = math.asin(max(-1., min(1., 2*(w*y-z*x))))
        self.initial_roll = math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))
        pitch_deg = math.degrees(self.initial_pitch)
        if abs(pitch_deg) >= 89:
            raise ValueError('Initial pitch is too close to the Euler singularity')
        self.tilt = JointController({'pitch': 0., 'roll': 0.},
            {'pitch': (-89-pitch_deg, 89-pitch_deg), 'roll': (-180., 180.)},
            {'pitch': 5., 'roll': 5.})
        self.reset()

    def reset(self):
        self.x, self.y, self.z, self.heading = self.initial
        self.tilt.reset()
        self.hold()

    def hold(self):
        self.speed = self.yaw_rate = 0.0
        self.tilt.hold(self.tilt.states, self.tilt_angles())

    def tilt_angles(self):
        return {name: state.angle for name, state in self.tilt.states.items()}

    def command_tilt(self, action, *, name=None, mode=None, commands=None):
        actual = self.tilt_angles()
        if action == 'mode':
            self.tilt.select_mode(name, mode, actual)
        elif action == 'execute':
            self.tilt.execute(commands, actual)
        elif action == 'hold':
            self.tilt.hold([name] if name else self.tilt.states, actual)
        else:
            raise ValueError('Unknown tilt command: '+action)

    def height(self, z):
        self.z, = finite(z)

    def direct(self, x, y, yaw_deg):
        x, y, yaw = finite(x, y, yaw_deg)
        self.x, self.y, self.heading = x, y, math.radians(yaw)
        self.speed = self.yaw_rate = 0.0

    def velocity(self, speed, yaw_rate_deg):
        speed, yaw = finite(speed, yaw_rate_deg)
        self.speed, self.yaw_rate = speed, math.radians(yaw)

    def step(self, dt):
        dt, = finite(dt)
        if dt < 0:
            raise ValueError('dt must be nonnegative')
        # Exact constant-twist integration, including reverse and turn-in-place.
        turn = self.yaw_rate * dt
        half = turn * 0.5
        distance = self.speed * dt * (math.sin(half)/half if abs(half) > 1e-9 else 1.0)
        self.x += distance * math.cos(self.heading + half)
        self.y += distance * math.sin(self.heading + half)
        self.heading += turn
        self.tilt.step(dt)

    @property
    def position(self):
        return (self.x, self.y, self.z)

    @property
    def orientation(self):
        # Column-vector convention: Rz(heading) Ry(initial_pitch+offset)
        # Rx(initial_roll+offset). USD/Gf transposition happens at the API boundary.
        angles = self.tilt_angles()
        if angles['pitch'] == 0 and angles['roll'] == 0:
            half = (self.heading-self.initial[3])*0.5
            return multiply_wxyz((math.cos(half), 0., 0., math.sin(half)), self.initial_orientation)
        yaw = self.heading*.5
        pitch = (self.initial_pitch+math.radians(angles['pitch']))*.5
        roll = (self.initial_roll+math.radians(angles['roll']))*.5
        return multiply_wxyz(multiply_wxyz(
            (math.cos(yaw),0.,0.,math.sin(yaw)),
            (math.cos(pitch),0.,math.sin(pitch),0.)),
            (math.cos(roll),math.sin(roll),0.,0.))

    def snapshot(self):
        return {'position_world_m': list(self.position), 'heading_deg': math.degrees(self.heading),
                'speed_m_s': self.speed, 'yaw_rate_deg_s': math.degrees(self.yaw_rate),
                'initial_pitch_deg': math.degrees(self.initial_pitch),
                'initial_roll_deg': math.degrees(self.initial_roll),
                'tilt_offsets': {name: asdict(state) for name, state in self.tilt.states.items()},
                'tilt_units': 'degrees and simulation seconds',
                'rotation_order': 'Rz(heading) Ry(initial_pitch+offset) Rx(initial_roll+offset); column vectors',
                'pivot': 'robot reference origin; no ground following'}
