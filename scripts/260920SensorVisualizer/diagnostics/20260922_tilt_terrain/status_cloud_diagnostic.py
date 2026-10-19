import json
from pathlib import Path
r=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/tilt_terrain')
out={}
for name in ['cloud_diagnostic.json','cloud_diagnostic_process.json']:
    p=r/name
    if p.is_file():out[name]=json.loads(p.read_text())
identity=out.get('cloud_diagnostic_process.json',{})
if identity:
    p=Path('/proc')/str(identity['pid'])
    out['process_exists']=p.exists()
    if p.exists():
        out['process_state']=(p/'stat').read_text().split()[2]
        out['same_process']=(p/'stat').read_text().split()[21]==identity['start_ticks']
log=r/'cloud_diagnostic_kit.log'
if log.exists():
    with log.open('rb') as f:
        f.seek(max(0,log.stat().st_size-7000));out['log_tail']=f.read().decode(errors='replace')
print(json.dumps(out))
