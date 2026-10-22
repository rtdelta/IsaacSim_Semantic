"""Deskew NONCOMPENSATED/SENSOR points using an epoch-local physics pose history.

Times are int64 nanoseconds. Quaternions are XYZW. No time-offset fitting or
extrapolation is permitted. Retain invalid/missing-return accounting upstream.
"""
import numpy as np


def rotate(q, xyz):
    v = q[..., :3]
    uv = 2 * np.cross(v, xyz)
    return xyz + q[..., 3:4] * uv + np.cross(v, uv)


class PoseHistory:
    def __init__(self, times_ns, positions, quaternions_xyzw):
        self.t = np.asarray(times_ns, dtype=np.int64)
        self.p = np.asarray(positions, dtype=float)
        self.q = np.asarray(quaternions_xyzw, dtype=float)
        n = len(self.t)
        if n < 2 or self.p.shape != (n, 3) or self.q.shape != (n, 4):
            raise ValueError('At least two matching poses are required')
        if np.any(np.diff(self.t) <= 0):
            raise ValueError('Times must increase strictly within one Play epoch')
        if not np.isfinite(self.p).all() or not np.isfinite(self.q).all():
            raise ValueError('Non-finite pose')
        norm = np.linalg.norm(self.q, axis=1, keepdims=True)
        if np.any(norm < 1e-12):
            raise ValueError('Zero quaternion')
        self.q = self.q / norm

    def sample(self, times_ns):
        t = np.atleast_1d(np.asarray(times_ns, dtype=np.int64))
        if np.any(t < self.t[0]) or np.any(t > self.t[-1]):
            raise ValueError('Ray/reference time is outside this epoch pose history')
        i = np.clip(np.searchsorted(self.t, t, side='right') - 1, 0, len(self.t)-2)
        u = ((t-self.t[i])/(self.t[i+1]-self.t[i]))[:, None]
        p = self.p[i]*(1-u) + self.p[i+1]*u
        q0, q1 = self.q[i], self.q[i+1].copy()
        dot = np.sum(q0*q1, axis=1, keepdims=True)
        q1 = np.where(dot < 0, -q1, q1)
        dot = np.clip(np.abs(dot), 0, 1)
        theta = np.arccos(dot)
        den = np.maximum(np.sin(theta), 1e-15)
        spherical = np.sin((1-u)*theta)/den*q0 + np.sin(u*theta)/den*q1
        q = np.where(dot > .9995, (1-u)*q0 + u*q1, spherical)
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        return p, q

    def deskew(self, raw_sensor_xyz, ray_times_ns, reference_time_ns=None):
        """Return world points, or points in the sensor frame at reference_time_ns."""
        xyz = np.asarray(raw_sensor_xyz, dtype=float)
        if xyz.shape != (len(ray_times_ns), 3):
            raise ValueError('Each point requires a ray time')
        p, q = self.sample(ray_times_ns)
        world = rotate(q, xyz) + p
        if reference_time_ns is None:
            return world
        pref, qref = self.sample([reference_time_ns])
        inverse = qref.copy()
        inverse[:, :3] *= -1
        return rotate(inverse, world-pref)
