"""Post-experiment installed-parser validation of all reported frame/time fields."""
import asyncio,gzip,hashlib,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows,save
from tools.native_rotation_localization.math_independent import decode
async def main():
 import numpy as np,omni.kit.app,omni.timeline
 from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
 app=omni.kit.app.get_app();suite=ROOT/'reports/native_rotation_localization/native007_20261015_v1';result={'scope':'Offline after all capture stages; installed parser frame/time/enum/scan fields against independent owned-byte decoder','files':[]}
 try:
  if omni.timeline.get_timeline_interface().is_playing():raise RuntimeError('No active simulation allowed')
  for manifest in sorted(suite.glob('*/*/*/*/continuous/raw_events.jsonl')):
   c=manifest.parent;paths={r['native_event']['packet_path']:r['native_event']['packet_sha256'] for r in rows(manifest)}
   paths.update({r['packet_path']:r['packet_sha256'] for r in rows(c/'api_polls.jsonl') if r.get('packet_path')})
   for path,expected in sorted(paths.items()):
    r={'path':str((c/path).relative_to(suite))}
    try:
     raw=gzip.decompress((c/path).read_bytes());h,a,xyz=decode(raw)
     if hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError('Payload SHA changed')
     owned=np.frombuffer(raw,dtype=np.uint8).copy();g=parse_generic_model_output_data(owned)
     checks={}
     for k,n in [('frame_start','frameStart'),('frame_end','frameEnd')]:
      frame=getattr(g,n);checks[k]=np.array_equal(frame.orientation,h[k]['quaternion_raw']) and np.array_equal(frame.posM,h[k]['position_m']) and int(frame.timestampNs)==int(h[k]['timestamp_ns'])
     for k,n in [('coordinates_type_code','elementsCoordsType'),('frame_of_reference_code','frameOfReference'),('motion_compensation_code','motionCompensationState'),('scan_complete','scanComplete')]:checks[k]=int(getattr(g,n))==h[k]
     checks['time_offset_ns']=np.array_equal(a['time_offset_ns'],np.asarray(g.timeOffsetNs))
     checks['tick_states']='tick_states' not in a or np.array_equal(a['tick_states'],np.asarray(g.tickStates))
     r.update(passed=all(checks.values()),checks={k:bool(v) for k,v in checks.items()})
    except Exception as exc:r.update(passed=False,error=str(exc))
    result['files'].append(r)
    if len(result['files'])%16==0:await app.next_update_async()
  result.update(passed=bool(result['files']) and all(r['passed'] for r in result['files']),decoded_files=len(result['files']))
 except Exception as exc:result.update(passed=False,failure=str(exc),traceback=traceback.format_exc())
 save(suite/'final_metadata_crosscheck.json',result);app.post_quit(0 if result['passed'] else 1)
asyncio.ensure_future(main())
