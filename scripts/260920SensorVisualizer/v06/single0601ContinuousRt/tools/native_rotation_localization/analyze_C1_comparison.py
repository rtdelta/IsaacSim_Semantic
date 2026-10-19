"""Compare failed C1 warmup semantics to baseline, without selecting 10 Hz samples."""
import gzip,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import rows,save
from tools.native_rotation_localization.math_independent import decode
suite=ROOT/'reports/native_rotation_localization/native007_20261015_v1';a=suite/'A0/S0/r01/q02/continuous';b=suite/'C1/S0/r01/cq01/continuous'
pa=json.loads((a/'sensor_manifest.json').read_text())['attributes'];pb=json.loads((b/'sensor_manifest.json').read_text())['attributes']
fa=json.loads((a/'configuration_fingerprint.json').read_text());fb=json.loads((b/'configuration_fingerprint.json').read_text())
def ids(c,r):
 h,x,_=decode(gzip.decompress((c/r['native_event']['packet_path']).read_bytes()));valid=(x['flags']&64)!=0
 i=np.column_stack([x[k][valid] for k in ('emitter_id','channel_id','tick_id','echo_id')]);return i[np.lexsort(i.T[::-1])]
def source(r):return round(float(r['IsaacReadSimulationTime']['simulationTime'])*1e9)
baseline_by_time={source(r):r for r in rows(a/'raw_events.jsonl')};events=rows(b/'raw_events.jsonl');matched=[]
for r in events:
 t=source(r)
 if t not in baseline_by_time:continue
 left,right=ids(a,baseline_by_time[t]),ids(b,r)
 matched.append({'source_ns':str(t),'same_full_valid_set':np.array_equal(left,right),'counts':[len(left),len(right)]})
result={'actual_sensor_differences':[k for k in set(pa)|set(pb) if pa.get(k)!=pb.get(k)],'effective_equal':fa['effective']==fb['effective'],'environment_equal':fa['environment']==fb['environment'],'scene_equal':fa['scene']==fb['scene'],
 'native_requested_tick_hz':pb['omni:sensor:tickRate']['value'],'native_requested_scan_hz':pb['omni:sensor:Core:scanRateBaseHz']['value'],'events':len(events),
 'same_source_event_comparisons':[{**r,'same_full_valid_set':bool(r['same_full_valid_set'])} for r in matched],
 'scope':'Single static initialization; all 22 outputs retained. Only native source timestamps shared with baseline can have identity sets paired; no decimation or replacement target selection. Dynamic C1 remains cadence-unqualified.',
 'supersedes':'warmup_baseline_comparison.json used one final baseline frame for all warmup events and its prose incorrectly implied equal valid sets; the boolean was false. This v2 uses exact shared source time for descriptive comparisons only.'}
save(b.parent/'warmup_baseline_comparison_v2.json',result);print(json.dumps(result))
