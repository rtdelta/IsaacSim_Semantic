"""Inventory this experiment's cases and verify all owned GPU jobs have exited."""
from pathlib import Path
import json,time,psutil
root=Path(__file__).resolve().parent
rows=[]
for d in sorted((root/'cases').iterdir()):
 if not d.is_dir():continue
 r=json.loads((d/'result.json').read_text()) if (d/'result.json').exists() else {}
 pr=json.loads((d/'process.json').read_text()) if (d/'process.json').exists() else {}
 rows.append({'case':d.name,'status':r.get('status','geometry_export' if (d/'geometry.json').exists() else 'no_result'),
  'exit_code':pr.get('exit_code'),'timed_out':pr.get('timed_out'),
  'wall_seconds':pr.get('wall_seconds'),'data_buffers':len(r.get('samples',r.get('views',[])))})
active=[]
for proc in psutil.process_iter(['pid','cmdline']):
 c=proc.info['cmdline'] or []
 if any(str(root)+'/' in x for x in c) and any(Path(x).name in [
   'motion_case.py','depth_case.py','export_geometry.py','run_case.py','run_suite.py'] for x in c):
  active.append({'pid':proc.pid,'cmdline':c})
out={'finished_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cases':rows,
     'active_owned_jobs':active,'source_verification':json.loads((root/'source_usda_verification.json').read_text())}
(root/'case_inventory.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'cases':len(rows),'collected':sum(x['status']=='collected' for x in rows),
                 'active_owned_jobs':active,'source_verification':out['source_verification']}))
assert not active and out['source_verification']['unchanged']

