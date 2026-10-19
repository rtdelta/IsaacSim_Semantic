import json
from pathlib import Path
p=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v06/benchmarks/1791604257379431843_v05/input_trajectory/states.jsonl')
rows=[json.loads(l) for l in p.read_text().splitlines() if l.strip()]
print(json.dumps({'rows':len(rows),'first':{k:rows[0][k] for k in ['position_world_m','quaternion_xyzw','joints_deg']},
 'tenth':{k:rows[min(9,len(rows)-1)][k] for k in ['position_world_m','quaternion_xyzw','joints_deg']},
 'last':{k:rows[-1][k] for k in ['position_world_m','quaternion_xyzw','joints_deg']}}))
