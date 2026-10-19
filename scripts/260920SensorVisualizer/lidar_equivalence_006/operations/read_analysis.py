import json
from pathlib import Path
R=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006');out=Path(json.loads((R/'reports/latest.json').read_text())['directory'])
p=out/'analysis.log';print(p.read_text()[-6000:] if p.exists() else 'no analysis log')
s=out/'analysis/summary.json'
if s.exists():
 d=json.loads(s.read_text());print(json.dumps({k:v for k,v in d.items() if k!='state_alignment'},indent=2))
 print(json.dumps({'state_alignment':[{'round':r['round'],'group':r['group'],'mesh_count':r['mesh_count_legacy'],'max_mesh_error':r['max_mesh_world_matrix_error'],'mesh_differences':r['mesh_differences'][:5],'parameter_differences':r['sensor_parameter_differences'][:5]} for r in d['state_alignment']]},indent=2))
