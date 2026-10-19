import json,sys
from pathlib import Path
import numpy as np
from analyze import compare,bag_verify
root=Path(sys.argv[1]);cap=root/'native_pause_no_probe/capture';out=root/'pause_confirmation';out.mkdir(exist_ok=True)
result=json.loads((cap/'result.json').read_text());assert result['engine_exit']==0
rows=[];states=[]
for p in sorted((cap/'formal_clouds').glob('*/*.npy')):
 group=p.parent.name;sid=p.stem;a=np.load(root/'legacy/round_02/capture/formal_clouds'/group/p.name);b=np.load(p)
 rows.append({'group':int(group),'sensor':sid,**compare(a,b)})
for p in sorted((cap/'state_evidence').glob('*.json')):
 a=json.loads(p.read_text());b=json.loads((root/'native/round_01/capture/state_evidence'/p.name).read_text())
 err=max(float(np.max(np.abs(np.array(v['world_matrix_row'])-np.array(b['meshes'][k]['world_matrix_row'])))) for k,v in a['meshes'].items())
 attrs=[(k,n) for k,v in a['sensor_attributes'].items() for n,x in v.items() if n.startswith('omni:sensor:') and x!=b['sensor_attributes'][k].get(n)]
 states.append({'group':int(p.stem),'mesh_matrix_max_error':err,'sensor_parameter_differences':attrs})
verification=bag_verify(cap,'native');(out/'bag_verification.json').write_text(json.dumps(verification,indent=2))
groups=[json.loads(l) for l in (cap/'groups.jsonl').read_text().splitlines()]
checks=[{'group':g['group'],'native_time_s':g['native_time_s'],'native_time_after_s':g['native_time_after_s'],'pose_change_error':g['pose_change_error'],'root_target_max_abs_error':g['root_target_max_abs_error'],'joint_target_max_abs_error_rad':g['joint_target_max_abs_error_rad']} for g in groups]
errors={}
for name in ('validation.json','group_validation.json'):
 p=cap/name
 if p.exists():d=json.loads(p.read_text());errors[name]={'ok':d['ok'],'errors':d['errors']}
summary={'case':'native_pause_no_probe','groups':len(groups),'samples':len(rows),'formal_mcap_verified':verification['passed'],'run_result':{k:result[k] for k in ('state','engine_exit','validation_exit','group_validation_exit')},'state_checks':states,'freeze_checks':checks,'validation':errors,'focus':[r for r in rows if r['sensor'] in ('MyNZ3_left','MyNZ3_right')]}
(out/'comparisons.json').write_text(json.dumps(rows,indent=2));(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
