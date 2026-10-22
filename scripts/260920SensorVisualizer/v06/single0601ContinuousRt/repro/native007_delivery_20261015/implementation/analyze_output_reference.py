"""Output-derived rotation candidates, explicitly below direct consumption evidence."""
import gzip,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows,save
from tools.native_rotation_localization.math_independent import decode,quantiles,yaw,wrap
from tools.native_rotation_localization.normalizer import normalize
from tools.native_rotation_localization.ray_model import rays
def analyze(path):
 p=Path(path);c=p/'continuous';params=json.loads((c/'sensor_manifest.json').read_text())['attributes']
 metrics=json.loads((p/'analysis/target_metrics.json').read_text());raw={r['receipt_seq']:r for r in rows(c/'raw_events.jsonl')};states={r['physical_step']:r['matrix'] for r in rows(c/'baseline_physics.jsonl') if r['phase']=='physics_post_actual'}
 output=[]
 for t in metrics:
  step=t['physical_step'];r=raw[t['receipt_seq']];h,a,xyz=decode(gzip.decompress((c/r['native_event']['packet_path']).read_bytes()));valid=(a['flags']&64)!=0
  ray,_=rays(params,a,h,valid);n=normalize(h,xyz[valid],states[step]);q=n['native_cartesian'];keep=np.hypot(ray[:,0],ray[:,1])>1e-6
  angles=wrap(np.arctan2(q[keep,1],q[keep,0])-np.arctan2(ray[keep,1],ray[keep,0]))
  current=yaw(states[step]);previous=yaw(states[step-1]);half=previous+wrap(current-previous)/2
  values={'current':current,'half':half,'previous1':previous,'previous2':yaw(states[step-2])}
  ref=h['frame_of_reference_code'];expected=values if ref else {'sensor_local':0.}
  errors={k:quantiles(abs(wrap(angles-v))) for k,v in expected.items()}
  quats={}
  for key in ('frame_start','frame_end'):
   x,y,z,w=h[key]['quaternion_raw'];quats[key]=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
  output.append({'target_index':t['target_index'],'physical_step':step,'motion_step':t['motion_step'],'output_reference_code':ref,
   'output_rotation_rad':quantiles(angles),'candidate_direction_errors_rad':errors,'actual_candidate_yaw_rad':values,'GMO_frame_yaw_rad':quats,
   'GMO_frame_candidate_errors_rad':{key:quantiles(abs(wrap(angles-v))) for key,v in quats.items()} if ref else None,
   'distance_candidate':t.get('candidate'),'scope':'rotation inferred from emitted-pattern nominal direction and output coordinates; not actual ray origin/direction or history-consumption trace'})
 return {'run':str(p),'evidence_level':'E2','targets':output}
if __name__=='__main__':save(Path(sys.argv[2]),analyze(sys.argv[1]))
