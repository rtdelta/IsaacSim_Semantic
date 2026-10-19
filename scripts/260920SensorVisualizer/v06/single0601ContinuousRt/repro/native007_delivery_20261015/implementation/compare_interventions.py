"""Single-factor comparison with explicit complete-scan and timing semantics."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.compare_layers import compare,read_run
from tools.native_rotation_localization.io import save
def analyze(left,right):
 a,b=read_run(left),read_run(right);result=compare(left,right)
 for run in (a,b):
  final=run['path']/'analysis_final/target_metrics.json'
  if final.is_file():run['metrics']=json.loads(final.read_text())
 ea,eb=a['fingerprint']['effective'],b['fingerprint']['effective']
 requested_a=a['spec']['requested_settings'];requested_b=b['spec']['requested_settings']
 expected={k for k in set(requested_a)|set(requested_b) if requested_a.get(k)!=requested_b.get(k)}
 actual={k for k in set(ea['settings'])|set(eb['settings']) if ea['settings'].get(k)!=eb['settings'].get(k)}
 effective_ok=expected==actual and {k:v for k,v in ea.items() if k!='settings'}=={k:v for k,v in eb.items() if k!='settings'}
 scans=[]
 for x,y in zip(a['metrics'],b['metrics']):
  hx,hy=x['native_header'],y['native_header'];rx,ry=x['representation'],y['representation']
  keys=('tick_ids','tick_state_counts','element_flag_counts','time_offset_ns')
  scans.append({'target_index':x['target_index'],'scan_complete':[hx['scan_complete'],hy['scan_complete']],
   'both_complete':hx['scan_complete']==hy['scan_complete']==1,
   'same_semantic_fields':{k:rx.get(k)==ry.get(k) for k in keys},
   'left_fields':{k:rx.get(k) for k in keys},'right_fields':{k:ry.get(k) for k in keys},
   'new_source_identity':[hx['native_frame_id'],hx['timestamp_ns'],hy['native_frame_id'],hy['timestamp_ns']]})
 semantic_ok=all(r['both_complete'] and all(r['same_semantic_fields'].values()) for r in scans)
 env_scene_ok=all(a['fingerprint'][k]==b['fingerprint'][k] for k in ('environment','scene'))
 complete=all(r['same_full_valid_ray_set'] for r in result['targets'])
 result.update(scope='single factor intervention',expected_setting_differences=sorted(expected),actual_setting_differences=sorted(actual),effective_single_factor_qualified=effective_ok,
   complete_scan_semantics_qualified=semantic_ok,scan_semantics=scans,
   comparison_qualified=bool(effective_ok and env_scene_ok and result['parameters_qualified'] and result['input_qualified'] and complete and semantic_ok and a['summary']['measurement_qualified'] and b['summary']['measurement_qualified']),
   scan_flag_limit='Installed header exposes tickStates values without bit meanings; compare raw distribution and scanComplete with full ray identities and new source events, do not invent a new-scan bit.')
 return result
if __name__=='__main__':save(Path(sys.argv[3]),analyze(sys.argv[1],sys.argv[2]))
