import datetime,json,hashlib
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');cfg=root/'config/native_instant_baseline'
order=json.loads((cfg/'run_order.json').read_text())
gate=json.loads((root/'reports/native_instant_baseline'/order['experiment_id']/'qualification_comparison.json').read_text())
if gate['all_measurement_and_pair_qualified'] is not True:raise RuntimeError('Six short runs and all three pairs must qualify')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
paths=set()
for folder in ('tools/native_instant_baseline','tools/clock_state','tools/experiments','single0601_continuous_rt'):
    paths.update(p for p in (root/folder).rglob('*.py'))
paths.update(p for p in (root.parent/'sensor_visualizer_v06').rglob('*.py'))
paths.update([root/'run_capture.py',root/'config/mixed_pair.json',cfg/'effective_E.json',cfg/'effective_D.json',cfg/'analysis_rules_v4.json',cfg/'run_order.json'])
paths.update(root/p for phase in ('qualification','main','D_qualification','D_main') for p in order[phase])
paths.update(cfg/(b+'.json') for b in order['batches'])
import os
lock={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'qualification_comparison_sha256':sha(root/'reports/native_instant_baseline'/order['experiment_id']/'qualification_comparison.json'),
    'files':[{'path':Path(os.path.relpath(p,root)).as_posix(),'sha256':sha(p)} for p in sorted(paths)]}
with (cfg/'main_code_lock.json').open('x') as f:json.dump(lock,f,indent=2)
print(json.dumps({'locked_files':len(paths),'lock_sha256':sha(cfg/'main_code_lock.json')}))
