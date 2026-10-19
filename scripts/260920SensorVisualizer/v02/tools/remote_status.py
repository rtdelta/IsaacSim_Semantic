from pathlib import Path
import json
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02/reports')
result = {}
for name in ('probe_process.json', 'probe_capture.json', 'capture_process.json'):
    p = root/name
    if p.is_file(): result[name] = json.loads(p.read_text())
for name in ('probe_kit.log', 'capture_kit.log'):
    p = root/name
    if p.is_file():
        lines = p.read_text(errors='replace').splitlines()
        relevant = [line for line in lines if any(s in line for s in ('[Error]', 'Traceback', 'Error:', 'Exception:', '[SV02', 'Warning]'))]
        result[name] = {'bytes': p.stat().st_size, 'tail': lines[-12:], 'issues': relevant[-30:]}
for p in sorted(root.glob('*/session.json'))[-4:]:
    result[str(p.relative_to(root))] = json.loads(p.read_text())
print(json.dumps(result, default=str))
