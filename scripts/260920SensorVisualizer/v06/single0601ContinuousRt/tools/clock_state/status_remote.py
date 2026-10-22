import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency')
out={}
for p in sorted(root.rglob('*.json')):
    if p.name in ('status.json','coordinator_status.json','summary.json','continuous_terminal.json','frozen_terminal.json'):
        data=json.loads(p.read_text());data.pop('spec',None);out[str(p.relative_to(root))]=data
out['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip()
print(json.dumps(out))
