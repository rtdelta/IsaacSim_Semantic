"""Bounded immutable CPU history with protected in-flight references."""
from collections import OrderedDict
from types import MappingProxyType
import json
from .common import ContractError, cjson


class StateLedger:
    def __init__(self, limit=1024):
        self.limit = limit
        self.records = OrderedDict()
        self.references = {}

    def publish(self, state):
        key = (state['epoch_id'], state['physical_step'])
        if key in self.records:
            raise ContractError('state_duplicate', 'A physical step may be published only once')
        while len(self.records) >= self.limit:
            candidate = next((k for k in self.records if not self.references.get(k)), None)
            if candidate is None:
                raise ContractError('state_history_full', 'All historical records are referenced by live tickets')
            del self.records[candidate]
        self.records[key] = cjson(state)  # serialized immutable snapshot, never USD or SDK handles

    def get(self, epoch, step):
        key = (epoch, step)
        if key not in self.records:
            raise ContractError('state_missing', 'No pre-render actual state for source physical step')
        return json.loads(self.records[key])

    def exact_time(self, epoch, time_ns, tolerance=2):
        candidates = [(step, json.loads(raw)) for (e, step), raw in self.records.items() if e == epoch]
        found = [(step, state) for step, state in candidates if abs(int(state['sim_time_ns']) - time_ns) <= tolerance]
        if len(found) != 1:
            raise ContractError('source_step_mismatch', 'Source time must identify exactly one actual physical step within 2 ns')
        return found[0]

    def retain(self, epoch, step):
        self.get(epoch, step)
        key = (epoch, step)
        self.references[key] = self.references.get(key, 0) + 1

    def release(self, epoch, step):
        key = (epoch, step)
        if self.references.get(key, 0) <= 0:
            raise ContractError('state_release', 'No live state reference')
        self.references[key] -= 1
