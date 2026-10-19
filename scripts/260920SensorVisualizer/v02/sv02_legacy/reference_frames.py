"""Horizontal reference frame math. Column vectors; quaternions are ROS XYZW."""
import math
import numpy as np


def quaternion_matrix(xyzw):
    q = np.asarray(xyzw, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
        raise ValueError('Reference quaternion must be finite and nonzero')
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


class HorizontalFrame:
    """Same origin, world-up Z, X aligned to the projected body X axis.

    Near a vertical body X axis, hold the last valid heading (zero if none).
    Hysteresis avoids threshold chatter. Quaternion signs stay continuous.
    """
    def __init__(self, epsilon=1e-6):
        if not math.isfinite(epsilon) or not 0 < epsilon < .1:
            raise ValueError('Heading epsilon must be finite and in (0, 0.1)')
        self.epsilon = epsilon
        self.reset()

    def reset(self):
        self.yaw = None
        self.valid = False
        self.previous_q = None
        self.last = None

    def update(self, position, xyzw):
        p = np.asarray(position, dtype=float)
        if p.shape != (3,) or not np.isfinite(p).all():
            raise ValueError('Reference position must contain three finite values')
        rotation = quaternion_matrix(xyzw)
        length = float(np.linalg.norm(rotation[:2, 0]))
        threshold = self.epsilon if self.valid else 2 * self.epsilon
        self.valid = length > threshold
        if self.valid:
            self.yaw = math.atan2(rotation[1, 0], rotation[0, 0])
        yaw = self.yaw if self.yaw is not None else 0.
        q = np.array([0., 0., math.sin(yaw/2), math.cos(yaw/2)])
        if self.previous_q is not None and np.dot(q, self.previous_q) < 0:
            q = -q
        self.previous_q = q.copy()
        self.last = {'position': p.tolist(), 'xyzw': q.tolist(),
                     'heading_rad': yaw, 'heading_valid': self.valid,
                     'projection_norm': length}
        return self.last
