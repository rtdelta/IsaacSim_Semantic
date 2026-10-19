"""Reconstruct the observed read corruption from evidence bytes only.

Does not load/execute the suspect ELF or connect to a remote instance.
"""
import base64
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
evidence = json.loads((root / 'targeted_evidence.json').read_text(encoding='utf-8'))
encoded = base64.b64decode(evidence['files']['/dev/shm/.dbus_sess']['base64'])
patterns = [bytes(c ^ 0x7f for c in line) + b':'
            for line in encoded.split(b'\n') if line]
result = {'method': 'Offline newline filtering reconstructed from static disassembly',
          'patterns': [p.decode() for p in patterns], 'files': {}}
for path, pair in evidence['read_pairs'].items():
    original = base64.b64decode(pair['raw'])
    observed = base64.b64decode(pair['normal'])
    chunks = original.split(b'\n')
    lines = [s + b'\n' for s in chunks[:-1]] + [chunks[-1]]
    removed = [s for s in lines if any(p in s for p in patterns)]
    reconstructed = b''.join(s for s in lines if not any(p in s for p in patterns))
    result['files'][path] = {
        'raw_bytes': len(original), 'normal_bytes': len(observed),
        'removed_bytes': sum(map(len, removed)), 'removed_lines': len(removed),
        'matches_normal_read_exactly': reconstructed == observed,
        'normal_sha256': hashlib.sha256(observed).hexdigest(),
        'reconstructed_sha256': hashlib.sha256(reconstructed).hexdigest(),
    }
(root / 'offline_filter_reproduction.json').write_text(
    json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result['files'], indent=2))
