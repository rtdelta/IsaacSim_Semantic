import json
from pathlib import Path
path=Path('/root/isaacsim/exts/isaacsim.core.simulation_manager/isaacsim/core/simulation_manager/impl/simulation_manager.py')
lines=path.read_text().splitlines();selected=set()
for i,line in enumerate(lines):
    if any(term in line for term in ('def get_simulation_time','def _on_physics','def _on_update','def _on_step','subscribe_physics_on_step_events','def get_num_physics_steps','def step(')):
        selected.update(range(max(0,i-4),min(len(lines),i+65)))
print(json.dumps({'path':str(path),'lines':['%d: %s'%(i+1,lines[i]) for i in sorted(selected)]}))
for parent in ('/root/isaacsim/exts','/root/isaacsim/kit/exts','/root/isaacsim/kit/extsPhysics','/root/isaacsim/extscache'):
    for folder in Path(parent).glob('*physx*'):
        for p in folder.glob('**/*.toml'):
            matches=['%d: %s'%(i+1,l) for i,l in enumerate(p.read_text(errors='replace').splitlines()) if any(s in l for s in ('minFrameRate','fixedTimeStep','useFixedTime','timeSteps','maxNumSteps'))]
            if matches:print(json.dumps({'path':str(p),'matches':matches}))
