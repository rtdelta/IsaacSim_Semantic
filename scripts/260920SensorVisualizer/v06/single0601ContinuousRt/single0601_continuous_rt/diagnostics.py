import json
import math
import time
from pathlib import Path
from .common import cjson


def process_resources():
    """Actual Linux process counters; unavailable fields stay null on other hosts."""
    import os
    path=Path('/proc/self/status')
    fields={}
    if path.exists():
        for line in path.read_text().splitlines():
            name,_,value=line.partition(':')
            if name in ('VmRSS','VmHWM','Threads'):
                fields[name]=int(value.strip().split()[0])
    return {'pid':os.getpid(),'rss_bytes':fields.get('VmRSS',0)*1024 if fields else None,
            'peak_rss_bytes':fields.get('VmHWM',0)*1024 if fields else None,
            'threads':fields.get('Threads'),'file_descriptors':len(list(Path('/proc/self/fd').iterdir())) if path.exists() else None,
            'monotonic_ns':str(time.monotonic_ns())}


class EvidenceLog:
    def __init__(self, directory, recording_id):
        self.directory, self.recording_id = Path(directory), recording_id
        self.files, self.sequences = {}, {}

    def event(self, filename, event_type, data, epoch=None, segment=None):
        if filename not in self.files:
            path = self.directory/filename
            path.parent.mkdir(parents=True, exist_ok=True)
            self.files[filename] = path.open('a', encoding='utf-8', buffering=8192)
            self.sequences[filename] = 0
        envelope = {'schema_version': 1, 'recording_id': self.recording_id, 'epoch_id': epoch, 'segment_id': segment,
                    'event_seq': self.sequences[filename], 'event_type': event_type,
                    'monotonic_ns': str(time.monotonic_ns()), 'data': data}
        self.files[filename].write(cjson(envelope).decode('utf-8')+'\n')
        self.sequences[filename] += 1

    def close(self):
        for file in self.files.values():
            file.flush()
            file.close()


def statistics(samples, definition, unit='ms'):
    values = sorted(samples)
    n = len(values)
    def rank(p):
        return values[max(0, math.ceil(p*n)-1)] if n else None
    median = (values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2) if n else None
    return {'n': n, 'median': median, 'p95': rank(.95), 'p99': rank(.99), 'max': values[-1] if n else None,
            'unit': unit, 'definition': definition + '; nearest-rank percentiles'}
