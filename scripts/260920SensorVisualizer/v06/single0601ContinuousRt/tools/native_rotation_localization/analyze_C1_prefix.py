"""Read all preserved C1 warmup outputs without inventing planned target samples."""
import collections,gzip,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows,save,verify
from tools.native_rotation_localization.math_independent import decode,quantiles
suite=ROOT/'reports/native_rotation_localization/native007_20261015_v1';p=suite/'C1/S0/r01/cq01';c=p/'continuous'
files=verify(c);physics={int(r['sim_time_ns']):r['physical_step'] for r in rows(c/'baseline_physics.jsonl') if r['phase']=='physics_post_actual'};out=[]
for r in rows(c/'raw_events.jsonl'):
 h,a,x=decode(gzip.decompress((c/r['native_event']['packet_path']).read_bytes()));source=round(float(r['IsaacReadSimulationTime']['simulationTime'])*1e9)
 steps=[s for t,s in physics.items() if abs(t-source)<=2];valid=(a['flags']&64)!=0
 out.append({'receipt_seq':r['receipt_seq'],'source_time_ns':str(source),'physical_steps':steps,'native_frame_id':h['native_frame_id'],'timestamp_ns':h['timestamp_ns'],'scan_complete':h['scan_complete'],
  'elements':h['num_elements'],'valid_count':int(valid.sum()),'tick_ids':np.unique(a['tick_id']).tolist(),'time_offset_ns':quantiles(a['time_offset_ns']),
  'tick_state_counts':{str(int(k)):int(v) for k,v in zip(*np.unique(a['tick_states'],return_counts=True))}})
steps=[r['physical_steps'][0] for r in out if len(r['physical_steps'])==1]
result={'state':'BLOCKED_OUTPUT_CADENCE_OR_SCAN_SEMANTICS','planned_targets':12,'target_phase_started':False,'captured_target_count':0,'preserved_warmup_events':len(out),'full_GMO_decoded':len(out),'verified_files':files,
 'source_step_stride_counts':dict(collections.Counter(b-a for a,b in zip(steps,steps[1:]))),'scan_complete_counts':dict(collections.Counter(r['scan_complete'] for r in out)),
 'native_identity_count':len({(r['native_frame_id'],r['timestamp_ns']) for r in out}),'cleanup':json.loads((p/'continuous_terminal.json').read_text())['cleanup'],
 'interpretation':'Unchanged 10 Hz request does not produce the qualified six-physics-step complete-scan event contract with accumulation disabled; do not decimate/relabel outputs to claim a fix. Other C1 profiles blocked; C2 remains independent.','events':out}
save(p/'warmup_semantics_analysis.json',result);print(json.dumps({k:v for k,v in result.items() if k!='events'}))
