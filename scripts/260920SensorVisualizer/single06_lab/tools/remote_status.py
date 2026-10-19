"""Read bounded results of the lab's latest owned execution."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/single06_lab')
record=json.loads((root/'reports/latest_execution.json').read_text());out=Path(record['directory'])
result={'execution':record,'supervisor_alive':Path('/proc') .joinpath(str(record['pid'])).exists()}
logs=list(out.parent.glob(out.name+'_supervisor.log'))+([out/'supervisor.log'] if (out/'supervisor.log').exists() else [])+([out.with_suffix('.log')] if out.with_suffix('.log').exists() else [])
for log in logs:
 with log.open('rb') as f:f.seek(max(0,log.stat().st_size-12000));result['supervisor_tail']=f.read().decode(errors='replace')
for rel in ('progress.json','result.json','capture_status.json','matrix_results.json','results.json'):
 p=out/rel
 if p.is_file():
  v=json.loads(p.read_text())
  if rel in ('matrix_results.json','results.json'):v=[{'spec':r['spec'],'exit_code':r.get('exit_code'),'capture':r.get('capture'),
      'validation':{k:(r.get('validation') or {}).get(k) for k in ('passed','groups','tf_matrix_max_abs_error')},'passed':r.get('passed')} for r in v]
  result[rel]=v
if not (out/'result.json').exists() or json.loads((out/'result.json').read_text()).get('exit_code') not in (None,0):
 log=out/'engine.log'
 if log.exists():
  with log.open('rb') as f:f.seek(max(0,log.stat().st_size-12000));result['engine_tail']=f.read().decode(errors='replace')
print(json.dumps(result,indent=2))
