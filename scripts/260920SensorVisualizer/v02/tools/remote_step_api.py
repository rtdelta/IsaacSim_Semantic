from pathlib import Path
import json
base=Path('/root/isaacsim/exts'); rows=[]
for folder in [base/'isaacsim.core.api',base/'isaacsim.core.simulation_manager']:
    for p in folder.rglob('*.py'):
        if p.stat().st_size>200000: continue
        lines=p.read_text().splitlines(); marks=[i for i,l in enumerate(lines) if any(term in l for term in ('def step(','def step_async(','def get_simulation_time','def set_physics_dt'))]
        positions=sorted({j for i in marks for j in range(max(0,i-2),min(len(lines),i+95))})
        if positions: rows.append({'path':str(p),'text':'\n'.join(lines[i] for i in positions)})
root=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v02')
finished=[p.parent for p in sorted(root.glob('20*/session.json')) if json.loads(p.read_text())['state']=='finished']
print(json.dumps({'sources':rows,'performance':json.loads((finished[-1]/'performance/summary.json').read_text())}))
