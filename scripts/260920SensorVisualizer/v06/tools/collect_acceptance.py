import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');directory=root/'reports/native_owner'
reports={}
for name in ('acceptance_status','native_keyboard_fix','lifecycle_fix','interaction','http_runtime','http_trajectory','motion_modes',
             'validation_offline','validation_live_latest','validation_live_complete','validation_stop_boundary',
             'concurrent_live_latest','concurrent_live_complete'):
    p=directory/(name+'.json')
    if p.exists():
        reports[name]=json.loads(p.read_text())
        if name=='http_trajectory':
            reports[name].pop('secret_values_logged',None)
            reports[name]['capability_output']='omitted'
owner=json.loads((directory/'owner.json').read_text());log=Path(owner['log']).read_text(errors='replace')
reports['owner_errors']=[x for x in log.splitlines() if any(s in x for s in ('Traceback','AttributeError','RuntimeError','AssertionError'))]
reports['owner_warning_count']=sum('[Warning]' in x for x in log.splitlines())
reports['note']='Native SDK events and loopback HTTP; human remote browser/desktop latency is unverified.'
old=root/'reports/acceptance_attempt_1_1791607838605353541/acceptance_status.json'
if old.exists():reports['first_attempt_preserved']=json.loads(old.read_text())
(root/'reports/native_acceptance_collected.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports))
