"""Finite offline sample plans shared by preview, task creation and replay."""
from fractions import Fraction
import json
import math

TIME_TOLERANCE_S = 1e-8


def sample_rate(value, physics_hz=60):
    try:
        if isinstance(value, bool) or isinstance(physics_hz, bool):raise ValueError()
        rate, physics = Fraction(str(value)), Fraction(str(physics_hz))
        if not 0 < rate <= physics or (physics / rate).denominator != 1:raise ValueError()
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        raise ValueError('sample_hz must be finite, positive and divide physics_hz') from None
    return rate


def request_options(payload, physics_hz=60):
    scope = payload.get('capture_scope', 'group_limit')
    if scope not in ('full_trajectory', 'group_limit'):raise ValueError('Unknown capture_scope')
    requested = payload.get('groups', 100 if 'capture_scope' not in payload else None)
    if scope == 'full_trajectory':
        if requested is not None:raise ValueError('Full trajectory conflicts with groups; omit groups')
    elif type(requested) is not int or requested < 1:
        raise ValueError('groups must be a positive integer')
    rate = sample_rate(payload.get('sample_hz', 10), physics_hz)
    return scope, requested, rate


def _duration(value):
    if isinstance(value, bool):raise ValueError('Invalid trajectory duration')
    try:value = float(value)
    except (TypeError,ValueError,OverflowError):raise ValueError('Invalid trajectory duration') from None
    if not math.isfinite(value) or value < 0:raise ValueError('Invalid trajectory duration')
    return value


def source_time_valid(group, duration, hz):
    return Fraction(group, 1) / Fraction(str(hz)) <= Fraction(str(_duration(duration))) + Fraction(str(TIME_TOLERANCE_S))


def make_plan(duration, payload, physics_hz=60):
    scope, requested, rate = request_options(payload, physics_hz)
    duration = _duration(duration)
    grid = (Fraction(str(duration)) + Fraction(str(TIME_TOLERANCE_S))) * rate
    available = grid.numerator // grid.denominator + 1
    planned = available if scope == 'full_trajectory' else min(requested, available)
    last = float(Fraction(planned - 1, 1) / rate)
    return {'schema_version': 1, 'scope': scope, 'requested_groups': requested,
            'sample_hz': float(rate), 'trajectory_duration_s': duration,
            'available_groups': available, 'planned_groups': planned,
            'first_sample_time_s': 0., 'last_sample_time_s': last,
            'time_tolerance_s': TIME_TOLERANCE_S,
            'unsampled_tail_s': max(0., duration - last)}


def verify_plan(plan, duration, groups, hz, physics_hz=60):
    if not isinstance(plan, dict):raise ValueError('Invalid capture_plan')
    payload = {'capture_scope': plan.get('scope'), 'sample_hz': hz, 'groups': plan.get('requested_groups')}
    expected = make_plan(duration, payload, physics_hz)
    if (type(groups) is not int or groups != expected['planned_groups'] or
            json.dumps(plan, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False)):
        raise ValueError('Capture plan differs from trajectory or job')
    return expected
