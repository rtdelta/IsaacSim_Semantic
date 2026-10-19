"""Separate full-output repetition eligibility from strict equal-return-set pairing."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.compare_layers import read_run
from tools.native_rotation_localization.io import save
def review(stage):
 suite=ROOT/'reports/native_rotation_localization/native007_20261015_v1';results=[]
 for p in sorted((suite/'stage_analysis'/stage).glob('pair_C*.json')):
  d=json.loads(p.read_text());a,b=read_run(d['left']),read_run(d['right'])
  structures=[]
  for r in d['scan_semantics']:
   x,y=r['left_fields'],r['right_fields']
   structures.append(r['both_complete'] and x['tick_ids']==y['tick_ids'] and x['time_offset_ns']==y['time_offset_ns'] and
    set(x['tick_state_counts'] or {})==set(y['tick_state_counts'] or {}) and set(x['element_flag_counts'] or {})==set(y['element_flag_counts'] or {}))
  eligible=bool(d['input_qualified'] and d['parameters_qualified'] and d['effective_single_factor_qualified'] and all(a['fingerprint'][k]==b['fingerprint'][k] for k in ('environment','scene')) and
   a['summary']['measurement_qualified'] and b['summary']['measurement_qualified'] and all(structures))
  results.append({'comparison':str(p.relative_to(suite)),'right':d['right'],'strict_pair_qualified':d['comparison_qualified'],'eligible_for_full_output_repeat':eligible,
   'same_flag_values_and_time_distribution':all(structures),'targets_with_unequal_valid_sets':sum(not r['same_full_valid_ray_set'] for r in d['targets']),
   'left_only_valid_ids_total':sum(r.get('left_only_ids',0) for r in d['targets']),'right_only_valid_ids_total':sum(r.get('right_only_ids',0) for r in d['targets']),
   'scope':'Repeat complete retained outputs and independent per-run nominal-model metrics; strict equal-return-set pair gate remains false where applicable. Do not filter intersections, claim matched full scans, or announce a fix.'})
 result={'stage':stage,'eligible_for_full_output_repeat':bool(results) and all(r['eligible_for_full_output_repeat'] for r in results),'comparisons':results,'strict_pair_gate_unchanged':True}
 save(suite/'stage_analysis'/stage/'intervention_confirmation_release.json',result);print(json.dumps(result));return result
if __name__=='__main__':review(sys.argv[1])
