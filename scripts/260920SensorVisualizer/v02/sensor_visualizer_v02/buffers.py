"""Single-owner mmap slots: no cross-Python shared-memory resource tracker."""
from pathlib import Path
import mmap
import os
import struct
import json
import numpy as np

MAX_CONTROL = 8 * 1024 * 1024


def send_message(sock, message):
    data = json.dumps(message, allow_nan=False, separators=(',', ':')).encode()
    if len(data) > MAX_CONTROL: raise ValueError('IPC control message too large')
    sock.sendall(struct.pack('!I', len(data)) + data)


def receive_message(sock):
    def exact(length):
        parts = bytearray()
        while len(parts) < length:
            chunk = sock.recv(length-len(parts))
            if not chunk: raise EOFError('Record worker disconnected')
            parts.extend(chunk)
        return parts
    size, = struct.unpack('!I', exact(4))
    if not 0 < size <= MAX_CONTROL: raise ValueError('Invalid IPC frame length')
    return json.loads(exact(size))


class SlotPool:
    def __init__(self, directory, count, capacity):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.capacity = capacity
        self.files, self.maps, self.generations = [], [], [0]*count
        self.in_use = {}
        for slot in range(count):
            path = self.directory/f'slot_{slot}.bin'
            stream = path.open('w+b')
            os.chmod(path, 0o600)
            stream.truncate(capacity)
            self.files.append(stream)
            self.maps.append(mmap.mmap(stream.fileno(), capacity))

    def reserve(self, group):
        for slot in range(len(self.maps)):
            if slot not in self.in_use:
                self.generations[slot] += 1
                self.in_use[slot] = (group, self.generations[slot])
                return slot
        return None

    def pack(self, slot, arrays):
        if slot not in self.in_use: raise RuntimeError('Slot is not reserved')
        offset, descriptors = 0, {}
        prepared = []
        for key, array in arrays.items():
            data = np.ascontiguousarray(array)
            if data.dtype.hasobject: raise ValueError('Object arrays are not valid IPC')
            offset = (offset+63)//64*64
            if offset+data.nbytes > self.capacity: raise BufferError('Frame exceeds slot_bytes; increase configured capacity')
            descriptors[key] = {'offset': offset, 'nbytes': data.nbytes, 'dtype': data.dtype.str, 'shape': list(data.shape)}
            prepared.append((offset, data))
            offset += data.nbytes
        for offset, data in prepared:
            self.maps[slot][offset:offset+data.nbytes] = memoryview(data).cast('B')
        group, generation = self.in_use[slot]
        return {'group_id': group, 'slot': slot, 'generation': generation,
                'used_bytes': offset, 'arrays': descriptors}

    def release(self, slot, group, generation):
        if self.in_use.get(slot) != (group, generation):
            raise RuntimeError('Stale or duplicate buffer release')
        del self.in_use[slot]

    def close(self):
        for mapping in self.maps: mapping.close()
        for stream in self.files:
            path = Path(stream.name)
            stream.close()
            path.unlink(missing_ok=True)
        self.maps.clear()
        self.files.clear()
        self.directory.rmdir()


def array_view(mapping, descriptor):
    dtype = np.dtype(descriptor['dtype'])
    shape = tuple(descriptor['shape'])
    if dtype.hasobject or any(type(n) is not int or n < 0 for n in shape): raise ValueError('Invalid IPC dtype/shape')
    offset = descriptor['offset']
    nbytes = int(np.prod(shape, dtype=object))*dtype.itemsize
    if type(offset) is not int or offset < 0 or nbytes != descriptor['nbytes'] or offset+nbytes > len(mapping):
        raise ValueError('IPC array exceeds buffer')
    array = np.ndarray(shape, dtype=dtype, buffer=mapping, offset=offset)
    array.flags.writeable = False
    return array
