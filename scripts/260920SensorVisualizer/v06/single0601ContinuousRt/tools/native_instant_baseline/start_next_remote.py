import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
order=json.loads((root/'config/native_instant_baseline/run_order.json').read_text())
for bid in order['batches']:
    status=root/'reports/native_instant_baseline/batches'/bid/'status.json'
    if status.exists():
        d=json.loads(status.read_text())
        if d['state']!='COMPLETE':raise RuntimeError('Existing unfinished/failed batch '+bid)
        continue
    subprocess.run(['/usr/bin/python3','-B',str(root/'tools/native_instant_baseline/coordinator.py'),'--batch',str(root/'config/native_instant_baseline'/(bid+'.json'))],check=True)
    break
else:print(json.dumps({'state':'all_declared_batches_complete'}))
