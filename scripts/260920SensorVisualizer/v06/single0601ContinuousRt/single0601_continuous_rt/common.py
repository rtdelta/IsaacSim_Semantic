import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


class ContractError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def cjson(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(cjson(value)).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_ns(value):
    if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ContractError('invalid_source_time', 'Source time must be finite physical seconds')
    ns = round(value * 1_000_000_000)
    if ns >= 2 ** 63:
        raise ContractError('time_overflow', 'Nanoseconds exceed int64')
    return ns
