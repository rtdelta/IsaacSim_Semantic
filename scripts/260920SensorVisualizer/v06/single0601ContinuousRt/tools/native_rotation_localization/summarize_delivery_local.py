"""Complete denominators and outcome categories from verified local delivery."""
import collections,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'reports/native007_delivery_20261015';E=BASE/'evidence'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
records=[]
for p in sorted(E.glob('*/*/*/*/analysis/summary.json')):
 parent=p.parent.parent;final=parent/'analysis_final/summary.json';s=read(final if final.exists() else p);spec=s['spec'];m=read((final if final.exists() else p).parent/'target_metrics.json')
 records.append({'path':parent.relative_to(E).as_posix(),'condition':spec['condition'],'profile':spec['profile'],'repeat':spec['repeat'],'run_id':spec['run_id'],
  'targets':s['planned_targets'],'measurement_qualified':s['measurement_qualified'],'static_model_qualified':s['static_model_qualified'],
  'distance_fail':s['distance_failed'],'direction_fail':s['direction_failed'],'absolute_fail':s['geometry_absolute_failed'],'increment_fail':s['geometry_increment_failed'],
  'plane_fail':sum(x.get('geometry',{}).get('point_plane_m',{}).get('0.95',0)>.005 for x in m),
  'yaw_fail':sum(abs(x['geometry']['yaw_error_rad'])>1e-4 for x in m if x.get('geometry',{}).get('yaw_error_rad') is not None),
  'yaw_unknown':sum(x.get('geometry',{}).get('yaw_error_rad') is None for x in m),
  'native_pose_fail':s['native_pose_failed'],'missing':s['target_missing'],'duplicate':s['target_duplicate'],'unassigned':s['unassigned_events'],'cleanup_ok':s['cleanup_ok'],
  'candidates':s['candidate_counts'],'candidate_status':dict(collections.Counter(x.get('candidate',{}).get('status','unavailable') for x in m)),
  'distinguishable_candidates':dict(collections.Counter('|'.join(x['candidate']['best_members']) for x in m if x.get('candidate',{}).get('status')=='distinguishable')),
  'yaw_median_deg':math.degrees(s['absolute_yaw_rad']['0.5']) if s['absolute_yaw_rad'] else None,
  'current_distance_p95_min_m':min(x.get('ray_residual_m',{}).get('0.95',float('inf')) for x in m),
  'current_distance_p95_max_m':max(x.get('ray_residual_m',{}).get('0.95',0) for x in m),
  'raw_events':s['raw_events'],'full_decoded':s['readback']['full_GMO_independently_decoded'],'readback_errors':s['readback']['errors'],
  'official_parser':s['official_parser_crosscheck'],'api_polls':s['api_polls'],'api_unique':s['api_unique_identities'],'api_matched':s['api_matched_native_events']})
sequences={p.parent.name:read(p) for p in (E/'sequences').glob('*/status.json')}
first=[r for key in ('qualification_q02','main_m02') for r in sequences[key]['runs']]
first_counts=collections.Counter(r['result']['state'] for r in first)
first_denominator={'planned_runs':len(first),'planned_targets':sum(r['targets'] for r in first),'states':dict(first_counts),
 'captured_runs':sum(r['result']['state'] in ('COMPLETE','FAILED_QUALIFICATION') for r in first),
 'captured_targets':sum(r['targets'] for r in first if r['result']['state'] in ('COMPLETE','FAILED_QUALIFICATION')),
 'blocked_runs':sum(r['result']['state'].startswith('BLOCKED') for r in first),'blocked_targets':sum(r['targets'] for r in first if r['result']['state'].startswith('BLOCKED'))}
groups=[]
for phase,runs in [('qualification',['q02']),('main',['m02']),('speed',['sm01']),('B3',['xq01']),('T3',['cq01']),('confirm',['cm01']),('coded',['code01'])]:
 subset=[r for r in records if r['run_id'] in runs]
 for condition,profile in sorted({(r['condition'],r['profile']) for r in subset}):
  rr=[r for r in subset if r['condition']==condition and r['profile']==profile];counts=collections.Counter();statuses=collections.Counter();distinct=collections.Counter()
  for r in rr:counts.update(r['candidates']);statuses.update(r['candidate_status']);distinct.update(r['distinguishable_candidates'])
  groups.append({'phase':phase,'condition':condition,'profile':profile,'runs':len(rr),'targets':sum(r['targets'] for r in rr),
   'all_measurement_qualified':all(r['measurement_qualified'] for r in rr),**{k:sum(r[k] for r in rr) for k in ('distance_fail','direction_fail','plane_fail','yaw_fail','yaw_unknown','absolute_fail','increment_fail','native_pose_fail','missing','duplicate','unassigned')},
   'candidates':dict(counts),'candidate_status':dict(statuses),'distinguishable_candidates':dict(distinct),'yaw_median_deg_by_repeat':[r['yaw_median_deg'] for r in rr]})
report={'first_matrix':first_denominator,'groups':groups,'records':records,'final_inventory':read(E/'final_inventory.json'),
 'stage_analyses':{p.parent.name:read(p) for p in (E/'stage_analysis').glob('*/summary.json')},'formal_continuous_acceptance':False,
 'overall_state':'PARTIAL_MANDATORY_COVERAGE' if first_denominator['blocked_runs'] else 'EXECUTED'}
(BASE/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'first_matrix':first_denominator,'all_preserved_runs':len(records),'groups':groups},ensure_ascii=False))
