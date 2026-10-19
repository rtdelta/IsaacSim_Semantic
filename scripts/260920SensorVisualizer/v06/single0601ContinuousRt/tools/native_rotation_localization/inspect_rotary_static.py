"""Static-only contract diagnostics, never a dynamic pose/range correction."""
import gzip,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows,save
from tools.native_rotation_localization.math_independent import decode,quantiles,ranges,pose,wrap
out=[]
base=ROOT/'reports/native_rotation_localization/native007_20261015_v1/A2'
for profile in ('S0','S5'):
 c=base/profile/'r01/q02/continuous';params=json.loads((c/'sensor_manifest.json').read_text())['attributes']
 def val(k):return params['omni:sensor:Core:'+k]['value']
 target=json.loads((c.parent/'analysis/target_metrics.json').read_text())[0]
 row=next(r for r in rows(c/'raw_events.jsonl') if r['receipt_seq']==target['receipt_seq'])
 h,a,xyz=decode(gzip.decompress((c/row['native_event']['packet_path']).read_bytes()));v=(a['flags']&64)!=0;xyz=xyz[v].astype(float)
 emitter=a['emitter_id'][v];ticks=a['tick_id'][v];fire=np.asarray(val('emitterState:s001:fireTimeNs'))[emitter]
 baseaz=np.asarray(val('emitterState:s001:azimuthDeg'))[emitter]+ticks*360.*val('scanRateBaseHz')/val('patternFiringRateHz')+val('startAzimuthOffsetDeg')
 el=np.deg2rad(np.asarray(val('emitterState:s001:elevationDeg'))[emitter]);actual_az=np.arctan2(-xyz[:,1],xyz[:,0]);dist=np.linalg.norm(xyz,axis=1)
 models={}
 for name,extra in [('tick_position_only',0.),('tick_plus_firetime',fire*360.*val('scanRateBaseHz')*1e-9)]:
  az=np.deg2rad(baseaz+extra);ray=np.column_stack((np.cos(el)*np.cos(az),-np.cos(el)*np.sin(az),np.sin(el)))
  models[name]={'azimuth_error_rad':quantiles(wrap(actual_az-az)),'distance_error_m':quantiles(abs(ranges(ray,pose(np.deg2rad(5. if profile=='S5' else 0.)))-dist))}
 out.append({'profile':profile,'effective_pattern_firing_hz':val('patternFiringRateHz'),'header':h,'tick_ids':[int(ticks.min()),int(ticks.max())],
  'point_time_offset_ns':quantiles(a['time_offset_ns'][v]),'models':models,
  'per_fire_time_azimuth_median_rad':{str(int(t)):float(np.median(wrap(actual_az[fire==t]-np.deg2rad(baseaz[fire==t])))) for t in np.unique(fire)}})
save(ROOT/'reports/native007_rotary_static_contract.json',out);print(json.dumps(out))
