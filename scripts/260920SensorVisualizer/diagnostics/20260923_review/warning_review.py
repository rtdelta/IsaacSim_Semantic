from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import json, re

log_root = Path('/root/.nvidia-omniverse/logs/Kit/Isaac-Sim Full/6.0')
paths = sorted(log_root.glob('kit_*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:2]
logs = []
for path in paths:
    groups = {}
    errors = []
    for line in path.read_text(errors='replace').splitlines():
        if '[Warning]' in line:
            message = line.split('[Warning]', 1)[1].strip()
            # Keep messages intact but group known variable prim addresses.
            key = re.sub(r'0x[0-9A-Fa-f]+', '0xADDR', message)
            entry = groups.setdefault(key, {'count': 0, 'first': line[:1200], 'last': line[:1200]})
            entry['count'] += 1
            entry['last'] = line[:1200]
        if '[Error]' in line or 'Traceback (most recent call last)' in line:
            errors.append(line[:1200])
    logs.append({'path': str(path), 'size': path.stat().st_size,
                 'modified_utc': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                 'warning_total': sum(e['count'] for e in groups.values()),
                 'warning_groups': sorted(groups.values(), key=lambda e: -e['count']),
                 'error_count': len(errors), 'errors_last': errors[-15:]})
processes = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        name = (p/'comm').read_text().strip()
        if name == 'kit':
            status = (p/'status').read_text().splitlines()
            processes.append({'pid': p.name, 'status': [s for s in status if s.startswith(('Name:', 'State:', 'Threads:', 'VmRSS:'))]})
    except OSError:
        pass
print(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'logs': logs, 'kit_processes': processes}, ensure_ascii=False))
