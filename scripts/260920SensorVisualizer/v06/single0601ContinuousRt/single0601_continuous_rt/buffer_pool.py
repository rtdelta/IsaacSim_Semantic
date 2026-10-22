"""Credit reserved before sampling; mmap descriptors carry identity and generation."""
from dataclasses import dataclass
import mmap
from pathlib import Path
from .common import ContractError


@dataclass
class Slot:
    index: int
    generation: int = 0
    identity: tuple = None
    released: bool = True
    encoded_pending: bool = False


class BufferPool:
    def __init__(self, directory, slot_bytes, budget_bytes, max_groups=1):
        self.slot_bytes, self.budget_bytes = slot_bytes, budget_bytes
        # Per group: owned raw + mmap + PNG/ROS/CDR double-buffer upper bound.
        # Two global slots cover native-arrival buffers and encoder scratch.
        self.groups = min(max_groups, (budget_bytes-2*slot_bytes)//(4*slot_bytes))
        if self.groups < 1:
            raise ContractError('buffer_budget', 'Insufficient total resident credit for one group and native-arrival safety')
        self.slots = [Slot(i) for i in range(self.groups)]
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.files, self.maps = [], []
        self.peak_bytes = 2*slot_bytes
        for slot in self.slots:
            path = self.directory / ('slot_%03d.mmap' % slot.index)
            f = path.open('w+b')
            f.truncate(slot_bytes)
            self.files.append(f)
            self.maps.append(mmap.mmap(f.fileno(), slot_bytes))

    @property
    def resident_credit_bytes(self):
        return 2*self.slot_bytes + sum(not s.released for s in self.slots)*2*self.slot_bytes + sum(s.encoded_pending for s in self.slots)*2*self.slot_bytes

    def reserve(self, identity):
        for slot in self.slots:
            if slot.released and not slot.encoded_pending:
                slot.generation += 1
                slot.identity, slot.released = tuple(identity), False
                slot.encoded_pending=True
                self.peak_bytes = max(self.peak_bytes, self.resident_credit_bytes)
                return slot.index, slot.generation
        return None

    def store(self, slot_id, generation, identity, arrays):
        slot = self.slots[slot_id]
        if slot.released or slot.generation != generation or slot.identity != tuple(identity):
            raise ContractError('stale_slot', 'Wrong slot generation or recording/group identity')
        needed = sum(a.nbytes for a in arrays.values())
        if needed > self.slot_bytes:
            raise ContractError('point_count_overflow', 'Actual complete group needs %d bytes; slot has %d; data will not be truncated' % (needed, self.slot_bytes))
        offset, descriptors = 0, {}
        for sid, array in sorted(arrays.items()):
            block = memoryview(array.reshape(-1)).cast('B')
            self.maps[slot_id][offset:offset+len(block)] = block
            descriptors[sid] = {'offset': offset, 'nbytes': len(block), 'shape': list(array.shape), 'dtype': array.dtype.str}
            offset += len(block)
        return {'path': str(Path(self.files[slot_id].name)), 'slot': slot_id, 'generation': generation,
                'identity': list(identity), 'slot_bytes': self.slot_bytes, 'arrays': descriptors}

    def release(self, slot_id, generation, identity):
        slot = self.slots[slot_id]
        if slot.released or slot.generation != generation or slot.identity != tuple(identity):
            raise ContractError('stale_ack', 'Old or mismatched release ACK cannot authorize slot reuse')
        slot.released = True

    def written(self,slot_id,generation,identity):
        slot=self.slots[slot_id]
        if not slot.released or not slot.encoded_pending or slot.generation!=generation or slot.identity!=tuple(identity):
            raise ContractError('stale_written_ack','Encoded credit requires the matching release then written ACK')
        slot.encoded_pending=False

    def close(self):
        if any(not s.released or s.encoded_pending for s in self.slots):
            raise ContractError('live_slot', 'Cannot close mmap while worker owns a slot')
        for mapped, f in zip(self.maps, self.files):
            mapped.close()
            f.close()
