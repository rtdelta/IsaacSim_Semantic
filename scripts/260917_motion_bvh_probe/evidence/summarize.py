import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
rows = []
for case in sorted((root / 'cases').iterdir()):
    def read(name):
        path = case / name
        return json.loads(path.read_text()) if path.exists() else {}
    result = read('result.json') or read('progress.json')
    samples = result.get('samples', [])
    log = (case / 'console.log').read_text(errors='replace')
    problems = [s for s in log.splitlines() if any(x in s.lower() for x in
        ['gaussians do not', 'motionbvh', '[error]', 'assertion', 'fatal', 'segmentation fault'])]
    row = {'case': case.name, 'process': read('process.json'),
           'status': result.get('status'), 'phase': result.get('phase'),
           'types': result.get('geometry', {}).get('type_counts'),
           'gaussians': result.get('geometry', {}).get('gaussian_candidates'),
           'settings': result.get('effective_settings'),
           'error': result.get('error'), 'cycles': {}, 'diagnostics': problems[:15],
           'diagnostic_count': len(problems)}
    for cycle in sorted(set(s['cycle'] for s in samples)):
        part = [s for s in samples if s['cycle'] == cycle]
        row['cycles'][str(cycle)] = {'buffers': len(part),
            'complete_buffers': sum(bool(s['scan_complete']) for s in part),
            'counts': sorted(set(s['count'] for s in part)),
            'nonfinite': sum(s['count'] - s['finite_count'] for s in part),
            'range_min': min(s['range_min'] for s in part),
            'range_max': max(s['range_max'] for s in part),
            'max_near_hits': max((s['near_hits_lt8m'] for s in part if 'near_hits_lt8m' in s), default=None),
            'wall_error_max_m': max((s['wall_error_max_m'] for s in part if 'wall_error_max_m' in s), default=None)}
    rows.append(row)
(root / 'summary.json').write_text(json.dumps(rows, indent=2))
if '--compact' in sys.argv:
    for row in rows:
        print(json.dumps({k: row[k] for k in ('case', 'status', 'error', 'cycles', 'diagnostic_count')}))
else:
    print(json.dumps(rows, indent=2))
