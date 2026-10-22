"""Final raw provenance, observer perturbation and narrow controls summary."""
import json,sys
from pathlib import Path
import numpy as np
from analyze import bag_verify,stats
root=Path(sys.argv[1]);out=root/'diagnostic_analysis';out.mkdir(exist_ok=True);rows=[]
for label,family in [('native_dual_retry1','native'),('legacy_raw_retry1','legacy'),('native_warm128_retry1','native'),('native_pause_retry1','native')]:
 cap=root/label/'capture';result=json.loads((cap/'result.json').read_text());r={'case':label,'run_result':{k:result[k] for k in ('state','exit_code','engine_exit','validation_exit','group_validation_exit') if k in result}}
 files=[p for p in sorted((cap/'dual_exit').glob('*/*.json')) if not p.name.endswith(('_object_map.json','_raw_header.json'))]
 d=[json.loads(p.read_text()) for p in files];r.update(samples=len(d),cpu_cuda_equal=sum(x['cpu_cuda_identical'] for x in d),cpu_stable=sum(x['cpu_stable'] for x in d),raw_stable=sum(x['raw_stable'] for x in d),raw_formal_equal=0,focus=[],observer_count_change=[],formal_vs_baseline_equal=0)
 for x in d:
  group=f"{x['group']:03d}";sid=x['sensor'];p=cap/'dual_exit'/group/(sid+'_raw.npz');a=np.load(p);raw=np.stack([a[k] for k in ('x','y','z')],axis=1);formal=np.load(cap/'formal_clouds'/group/(sid+'.npy'));base=np.load(root/family/'round_01/capture/formal_clouds'/group/(sid+'.npy'))
  r['raw_formal_equal']+=int(np.array_equal(raw,formal));r['observer_count_change'].append(len(formal)-len(base));r['formal_vs_baseline_equal']+=int(np.array_equal(formal,base))
  if sid in ('MyNZ3_left','MyNZ3_right'):
   r['focus'].append({'group':x['group'],'sensor':sid,'raw_frame':x['raw_before']['frameId'],'raw_stamp_ns':x['raw_before']['timestampNs'],'formal_stamp_s':x['stamp_s'],**stats(formal)})
 try:
  v=bag_verify(cap,family);r['bag_verified']=v['passed'];(out/(label+'_bag_verification.json')).write_text(json.dumps(v,indent=2))
 except Exception as exc:r['bag_verified']=False;r['bag_error']=type(exc).__name__+': '+str(exc)
 r['min_point_delta_from_baseline']=min(r['observer_count_change'],default=None);r['max_point_delta_from_baseline']=max(r['observer_count_change'],default=None)
 del r['observer_count_change'];rows.append(r)
repeat23={}
for family in ('legacy','native'):
 first=root/family/'round_02/capture/formal_clouds';second=root/family/'round_03/capture/formal_clouds';pairs=[(p,second/p.relative_to(first)) for p in first.glob('*/*.npy')]
 repeat23[family]={'pairs':len(pairs),'exact':sum(np.array_equal(np.load(a),np.load(b)) for a,b in pairs)}
(out/'summary.json').write_text(json.dumps({'cases':rows,'round2_round3_repeatability':repeat23},indent=2));print(json.dumps({'cases':rows,'round2_round3_repeatability':repeat23},indent=2))
