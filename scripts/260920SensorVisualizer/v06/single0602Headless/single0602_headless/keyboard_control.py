"""Epoch protected pressed-state integration in the current horizontal frame."""
import math
import time
from .robot.reference_frames import HorizontalFrame

PAIRS = {'boom': ('U', 'J'), 'arm': ('I', 'K'), 'bucket': ('O', 'L')}
KEYS = frozenset('W S A D Z X Q E R F T G U J I K O L'.split())

class KeyboardControl:
    def __init__(self, notify=None):
        self.sources = {}; self.enabled = False
        self.linear_speed, self.angular_speed, self.joint_speed = .5, 10., 10.
        self.input_epoch = 0; self.active_source = None; self.sequences = {}
        self.reason = 'initial_disabled'; self.notify = notify or (lambda *a, **k: None)
        self.received_ns = self.input_revision = self.applied_revision = 0
        self.last_apply_ms = None; self.horizontal = HorizontalFrame()

    def clear(self, reason='cleared', source=None):
        if source is not None and self.active_source != source:
            self.sources.pop(source, None); return False
        self.sources.clear(); self.active_source = None; self.input_epoch += 1
        self.sequences.clear(); self.reason = reason
        self.notify('input_cleared', reason=reason, input_epoch=self.input_epoch, source=source)
        return True

    def configure(self, payload):
        if 'enabled' in payload and type(payload['enabled']) is not bool:
            raise ValueError('Keyboard enabled must be a boolean')
        values = {}
        for key in ('linear_speed', 'angular_speed', 'joint_speed'):
            if key in payload:
                if isinstance(payload[key], bool): raise ValueError('Invalid keyboard speed')
                value = float(payload[key])
                if not math.isfinite(value) or not 0 < value <= 100: raise ValueError('Invalid keyboard speed')
                values[key] = value
        self.enabled = payload.get('enabled', self.enabled)
        for key, value in values.items(): setattr(self, key, value)
        self.clear('keyboard_configuration')
        self.notify('keyboard_configuration_applied', **self.status())

    def update(self, source, keys, epoch, sequence):
        if not isinstance(source, str) or not source or len(source) > 128: raise ValueError('Invalid input source')
        if not isinstance(keys, (list, tuple, set, frozenset)) or len(keys) > len(KEYS) or any(k not in KEYS for k in keys):
            raise ValueError('Unsupported key')
        if type(epoch) is not int or epoch != self.input_epoch: raise ValueError('Stale input epoch; read applied engine state')
        if type(sequence) is not int or sequence <= self.sequences.get(source, -1): raise ValueError('Out of order input sequence')
        if not self.enabled: raise ValueError('Keyboard mode is disabled')
        keys = set(keys)
        if not keys and self.active_source != source:
            self.sequences[source] = sequence; return False
        if keys and self.active_source not in (None, source): self.clear('input_source_changed')
        self.sequences[source] = sequence; self.active_source = source
        self.sources = {source: (keys, time.monotonic())}
        self.received_ns = time.monotonic_ns(); self.input_revision += 1
        return True

    def source_keys(self, source): return set(self.sources.get(source, (set(), 0))[0])

    def pressed(self):
        if not self.enabled or self.active_source is None: return set()
        keys, stamp = self.sources[self.active_source]
        if self.active_source != 'native' and time.monotonic() - stamp > .5:
            self.clear('browser_input_timeout', source=self.active_source); return set()
        return set(keys)

    def status(self):
        return {'enabled': self.enabled, 'input_epoch': self.input_epoch, 'source': self.active_source,
                'reason': self.reason, 'linear_speed': self.linear_speed,
                'angular_speed': self.angular_speed, 'joint_speed': self.joint_speed}

    def step(self, motion, dt):
        if not math.isfinite(dt) or dt < 0: raise ValueError('Invalid control step')
        keys = self.pressed()
        if not keys or not dt: return False
        c = motion.base_controller
        def value(pos, neg): return int(pos in keys) - int(neg in keys)
        w, x, y, z = c.orientation
        frame = getattr(motion, 'horizontal', self.horizontal).update(c.position, (x, y, z, w))
        heading = frame['heading_rad']
        forward, side = value('W', 'S'), value('A', 'D')
        distance = self.linear_speed * dt / max(1., math.hypot(forward, side))
        c.speed = c.yaw_rate = 0.
        c.x += distance * (forward * math.cos(heading) - side * math.sin(heading))
        c.y += distance * (forward * math.sin(heading) + side * math.cos(heading))
        c.z += self.linear_speed * dt * value('Z', 'X')
        c.heading += math.radians(self.angular_speed * dt * value('Q', 'E'))
        for name, pair in {'roll': ('R', 'F'), 'pitch': ('T', 'G')}.items():
            state = c.tilt.states[name]; state.running = False
            state.angle = max(state.minimum, min(state.maximum, state.angle + self.angular_speed * dt * value(*pair)))
        for joint in motion.config['joints']:
            state = motion.controller.states[joint['name']]; state.running = False
            state.angle = max(state.minimum, min(state.maximum,
                state.angle + self.joint_speed * dt * value(*PAIRS[joint['role']])))
        return True
