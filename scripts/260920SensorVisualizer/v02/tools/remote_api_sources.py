from pathlib import Path
import json
base = Path('/root/isaacsim')
files = [
 ('exts/isaacsim.sensors.rtx.nodes/isaacsim/sensors/rtx/nodes/impl/extension.py', 40, 180),
 ('exts/isaacsim.sensors.rtx.nodes/isaacsim/sensors/rtx/nodes/tests/test_point_cloud_annotator.py', 75, 155),
 ('exts/isaacsim.core.simulation_manager/isaacsim/core/simulation_manager/impl/simulation_manager.py', 0, 0),
]
for name, begin, end in files:
    p = base/name
    if not p.is_file(): continue
    lines = p.read_text(errors='replace').splitlines()
    if end:
        selected = range(begin-1, min(end,len(lines)))
    else:
        indexes = [i for i,l in enumerate(lines) if any(s in l for s in ('def get_simulation_time', 'def set_simulation_time', 'def get_num_physics_steps'))]
        selected = sorted(set(j for i in indexes for j in range(max(0,i-2), min(len(lines),i+24))))
    print(name+'\n'+'\n'.join(f'{i+1}: {lines[i]}' for i in selected))
for p in (base/'exts/isaacsim.core.nodes').rglob('*.pyi'):
    lines = p.read_text(errors='replace').splitlines()
    print(str(p)+'\n'+'\n'.join(l for l in lines if any(s in l.lower() for s in ('sim_time','simulation_time','physics_steps','reset'))))
