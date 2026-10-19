"""Exact physical-step join; no interpolation, timestamp shifts or arrival-order keys."""
from dataclasses import dataclass, field
import time
import numpy as np
from .common import ContractError
from .sensor_backend import pose_error


@dataclass
class GroupTicket:
    recording_id: str
    epoch_id: str
    segment_id: str
    group_id: int
    target_index: int
    target_step: int
    simulation_time_ns: str
    expected_sensor_ids: list
    slot: int
    generation: int
    reserved_monotonic_ns: str
    deadline_monotonic_ns: str
    received: dict = field(default_factory=dict)
    state: dict = None
    retained: bool = False

    def schedule(self):
        return {k: getattr(self, k) for k in ('recording_id','epoch_id','segment_id','group_id','target_index','target_step',
                'simulation_time_ns','expected_sensor_ids','slot','generation','reserved_monotonic_ns','deadline_monotonic_ns')}


class TimeJoiner:
    def __init__(self, ledger, recording_id, epoch_id, expected, config):
        self.ledger, self.recording_id, self.epoch_id = ledger, recording_id, epoch_id
        self.expected, self.config = set(expected), config
        self.tickets, self.events = {}, set()
        self.duplicate = self.invalid = self.late = 0

    def reserve(self, ticket):
        if (ticket.recording_id, ticket.epoch_id) != (self.recording_id, self.epoch_id) or set(ticket.expected_sensor_ids) != self.expected:
            raise ContractError('ticket_identity', 'Ticket identity and expected selection must match the locked session')
        if ticket.target_step in self.tickets:
            raise ContractError('ticket_duplicate', 'A target step may be scheduled once')
        self.tickets[ticket.target_step] = ticket

    def publish_state(self, state):
        ticket = self.tickets.get(state['physical_step'])
        if ticket:
            if abs(int(state['sim_time_ns']) - int(ticket.simulation_time_ns)) > 2:
                raise ContractError('physics_grid', 'Actual physical step differs from rational target grid')
            self.ledger.retain(ticket.epoch_id, ticket.target_step)
            ticket.retained = True

    def receive(self, evidence, payload, epoch_id, scene_generation):
        if epoch_id != self.epoch_id:
            raise ContractError('epoch_mismatch', 'Callback belongs to a different epoch')
        sid = evidence['sensor_id']
        if sid not in self.expected:
            raise ContractError('unrequested_sensor', 'Unexpected sensor receipt')
        step, state = self.ledger.exact_time(epoch_id, int(evidence['source_time_ns']))
        ticket = self.tickets.get(step)
        if ticket is None:
            return None, 'unrequested'
        if time.monotonic_ns() > int(ticket.deadline_monotonic_ns):
            self.late += 1
            raise ContractError('group_deadline', 'Native receipt missed its reserved wall-clock deadline')
        if state['scene_generation'] != scene_generation or evidence.get('ownership') != 'owned_cpu':
            raise ContractError('state_or_ownership', 'Wrong scene instance or borrowed payload')
        if not isinstance(payload, np.ndarray) or not payload.flags.owndata or not payload.flags.c_contiguous or payload.flags.writeable is False:
            raise ContractError('payload_ownership', 'Receipt must contain an independent contiguous CPU ndarray')
        native = evidence['native_ref']
        if native['kind'] == 'rational_time':
            if native['numerator'] is None or native['denominator'] is None or int(native['denominator']) <= 0:
                raise ContractError('native_reference', 'Malformed native rational event')
            event_key = (epoch_id, sid, native['scope'], native['numerator'], native['denominator'])
        else:
            if not native.get('event_id'):
                raise ContractError('native_reference', 'Equivalent native reference requires an event ID')
            event_key = (epoch_id, sid, native['scope'], native['event_id'])
        if sid in ticket.received:
            old_e, old_payload = ticket.received[sid]
            if old_e['native_ref'] == native and np.array_equal(old_payload, payload):
                self.duplicate += 1
                return None, 'duplicate'
            raise ContractError('conflicting_duplicate', 'Duplicate sensor callback conflicts with the accepted event or payload')
        if event_key in self.events:
            raise ContractError('stale_native_event', 'A native event cannot be submitted to multiple targets')
        provenance = evidence.get('source_time_provenance', {})
        if provenance.get('clock_domain') != 'physics_simulation' or provenance.get('mapping_method') in ('callback_current_time', None, ''):
            raise ContractError('source_provenance', 'Same-event mapped physical time required')
        delta = int(evidence['source_time_ns']) - int(state['sim_time_ns'])
        if abs(delta) > 2 or step != ticket.target_step:
            raise ContractError('source_time_mismatch', 'Receipt must belong to the exact actual physical target step')
        if int(state['snapshot_monotonic_ns']) > int(evidence['received_monotonic_ns']):
            raise ContractError('state_phase', 'Actual state must be published before the payload completion')
        translation, angle = pose_error(state['sensor_world_matrices_usd'][sid], evidence['rendered_to_world'])
        if translation > self.config['translation_tolerance_m'] or angle > self.config['rotation_tolerance_rad']:
            raise ContractError('rendered_pose_mismatch', 'Rendered sensor pose differs from the historical actual state')
        evidence = dict(evidence, source_time_error_ns=str(delta), to_world=state['sensor_world_matrices_usd'][sid],
                        translation_error_m=translation, rotation_error_rad=angle)
        ticket.received[sid] = (evidence, payload)
        ticket.state = state
        self.events.add(event_key)
        if set(ticket.received) == self.expected:
            checks = {'all_sensors_present': True, 'source_time_ok': True, 'pose_ok': True,
                      'freshness_ok': True, 'state_epoch_ok': True,
                      'max_abs_source_time_error_ns': str(max(abs(int(e['source_time_error_ns'])) for e, _ in ticket.received.values())),
                      'max_translation_error_m': max(e['translation_error_m'] for e, _ in ticket.received.values()),
                      'max_rotation_error_rad': max(e['rotation_error_rad'] for e, _ in ticket.received.values())}
            return {'ticket': ticket, 'state': state, 'receipts': ticket.received, 'sync_checks': checks,
                    'validated_monotonic_ns': str(time.monotonic_ns())}, 'accepted'
        return None, 'accepted'

    def expire(self):
        now = time.monotonic_ns()
        for ticket in self.tickets.values():
            if set(ticket.received) != self.expected and now > int(ticket.deadline_monotonic_ns):
                raise ContractError('missing_sensor', 'Missing selected sensors: ' + ','.join(sorted(self.expected-set(ticket.received))))

    def finish(self, step):
        ticket = self.tickets.pop(step)
        if ticket.retained:
            self.ledger.release(ticket.epoch_id, step)
        # The ledger rejects unavailable old state and the ticket key rejects unscheduled
        # targets. Only in-flight native IDs need storage; no growing event history.
        for evidence, _ in ticket.received.values():
            ref = evidence['native_ref']
            key = (ticket.epoch_id, evidence['sensor_id'], ref['scope'], ref['numerator'], ref['denominator']) if ref['kind']=='rational_time' else (ticket.epoch_id, evidence['sensor_id'], ref['scope'], ref['event_id'])
            self.events.discard(key)
