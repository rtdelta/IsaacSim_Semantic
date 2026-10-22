"""Preregistered metadata endpoint predictions; never relabel as consumed GPU history."""
import collections,gzip,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.compare_layers import read_run
from tools.native_rotation_localization.math_independent import decode,pose,ranges,quantiles,wrap,yaw
from tools.native_rotation_localization.normalizer import normalize
from tools.native_rotation_localization.ray_model import rays
from tools.native_rotation_localization.io import save
def analyze(path):
 run=read_run(path);out=[]
 for m in run['metrics']:
  event=run['raw'][m['receipt_seq']];h,a,xyz=decode(gzip.decompress((run['c']/event['native_event']['packet_path']).read_bytes()));valid=(a['flags']&64)!=0
  step=m['physical_step'];ray,_=rays(run['sensor'],a,h,valid);normalized=normalize(h,xyz[valid],run['states'][step]);angles={};norms={}
  for key in ('frame_start','frame_end'):
   x,y,z,w=h[key]['quaternion_raw'];angles[key]=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z));norms[key]=x*x+y*y+z*z+w*w
   if np.linalg.norm(h[key]['position_m'])>1e-8 or abs(x)>1e-8 or abs(y)>1e-8:raise ValueError('Header model scope is zero-origin Z-only rotation')
  angles['header_midpoint']=angles['frame_start']+wrap(angles['frame_end']-angles['frame_start'])/2
  residual={k:quantiles(abs(ranges(ray,pose(v))-normalized['distance'])) for k,v in angles.items()}
  current=yaw(run['states'][step]);previous=yaw(run['states'][step-1]);increment=wrap(current-previous)
  errors={k:{'current':abs(wrap(v-current)),'previous1':abs(wrap(v-previous))} for k,v in angles.items()}
  out.append({'target_index':m['target_index'],'motion_step':m['motion_step'],'physical_increment_rad':increment,
   'distance_candidate':m['candidate'],'header_yaw_rad':angles,'header_quaternion_norm_squared':norms,
   'header_actual_pose_error_rad':errors,'header_midpoint_distance_p95_m':residual['header_midpoint']['0.95'],
   'predicted_distance_residual_m':residual,'header_endpoint_increment_rad':wrap(angles['frame_end']-angles['frame_start']),
   'header_end_matches_current':errors['frame_end']['current']<=1e-6,'header_end_matches_previous1':errors['frame_end']['previous1']<=1e-6})
 return {'run':str(path),'targets':out,'header_midpoint_passed':sum(r['header_midpoint_distance_p95_m']<=1e-5 for r in out),
  'header_end_current':sum(r['header_end_matches_current'] for r in out),'header_end_previous1':sum(r['header_end_matches_previous1'] for r in out),
  'scope':'E2 output metadata prediction, fixed midpoint of reported endpoints; not a trace of actual consumed transforms, not proof of interpolation implementation',
  'parameter_fitting':False}
if __name__=='__main__':save(Path(sys.argv[2]),analyze(sys.argv[1]))
