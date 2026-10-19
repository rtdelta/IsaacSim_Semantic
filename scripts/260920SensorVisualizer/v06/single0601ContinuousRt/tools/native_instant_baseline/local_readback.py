"""Recompute a transferred representative run on the local Python runtime."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_instant_baseline.io import verify,rows,save,sha
from tools.native_instant_baseline.math_independent import decode,geometry,ranges,quantiles,classify

def run(parent):
    parent=Path(parent);c=parent/'continuous';files=verify(c);spec=json.loads((parent/'run_spec.json').read_text());metrics=json.loads((parent/'analysis/target_metrics.json').read_text())
    actual={r['physical_step']:r['matrix'] for r in rows(c/'baseline_physics.jsonl') if r['phase']=='physics_post_actual'}
    events=rows(c/'raw_events.jsonl' if spec['group'].startswith('M') else c/'raw_receipts.jsonl');byseq={r['receipt_seq']:r for r in events}
    attrs=json.loads((c/'sensor_manifest.json').read_text())['attributes'];az=np.deg2rad(np.asarray(attrs['omni:sensor:Core:emitterState:s001:azimuthDeg']['value'],float));el=np.deg2rad(np.asarray(attrs['omni:sensor:Core:emitterState:s001:elevationDeg']['value'],float))
    nominal=np.column_stack((np.cos(el)*np.cos(az),-np.cos(el)*np.sin(az),np.sin(el)));decoded={}
    for event in events:
        raw=(c/event['payload_path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==event['payload_sha256']
        xyz=np.frombuffer(raw,dtype='<f4').reshape(event['shape']);gmo=event['native_event'];raw=gzip.decompress((c/gmo['packet_path']).read_bytes())
        assert hashlib.sha256(raw).hexdigest()==gmo['packet_sha256'];header,arrays,allxyz=decode(raw);valid=(arrays['flags']&64)!=0;assert np.array_equal(allxyz[valid],xyz)
        decoded[event['receipt_seq']]=(xyz,nominal[arrays['emitter_id'][valid]])
    differences=[]
    for m in metrics:
        xyz,ray=decoded[m['receipt_seq']];state=actual[m['physical_step']];dist=np.linalg.norm(xyz.astype(float),axis=1);g=geometry(xyz,state);r=quantiles(abs(ranges(ray,state)-dist))
        candidate=classify(ray,dist,actual,m['physical_step']);dy=g['yaw_error_rad']-m['geometry']['yaw_error_rad'];dr=r['0.95']-m['ray_residual_m']['0.95']
        differences.append({'target_index':m['target_index'],'yaw_difference_rad':dy,'ray_p95_difference_m':dr,'candidate_equal':candidate['best_members']==m['candidate']['best_members']})
    result={'local_python':sys.version,'group':spec['group'],'verified_files':files,'full_GMO_decoded':len(decoded),'targets_recomputed':len(metrics),
        'all_agree':all(abs(d['yaw_difference_rad'])<1e-10 and abs(d['ray_p95_difference_m'])<1e-10 and d['candidate_equal'] for d in differences),'differences':differences}
    save(parent/'local_readback.json',result);print(json.dumps({k:v for k,v in result.items() if k!='differences'}))
if __name__=='__main__':run(sys.argv[1])
