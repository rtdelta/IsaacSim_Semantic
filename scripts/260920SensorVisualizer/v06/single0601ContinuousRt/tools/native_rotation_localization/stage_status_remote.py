import json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');suite=root/'reports/native_rotation_localization/native007_20261015_v1'
out={'free_bytes':shutil.disk_usage(root).free,'sequences':[],'stages':[]}
for p in sorted((suite/'sequences').glob('*/status.json')):
 d=json.loads(p.read_text())
 if d['id'].startswith('qualification_'):continue
 out['sequences'].append({'id':d['id'],'state':d['state'],'completed':len(d['runs']),'planned':d['planned_runs'],'active':d.get('active',{}).get('spec'),'failure':d.get('failure'),'last':d['runs'][-1:]})
for p in sorted((suite/'stage_analysis').glob('*/summary.json')):
 d=json.loads(p.read_text());out['stages'].append({'stage':d['stage'],'all_pair_qualified':d['all_pair_qualified'],'header_predictions':d['header_predictions'],'world_output_predictions':d['world_output_predictions'],
  'pairs':[{k:v for k,v in r.items() if k in ('right','comparison_qualified','quality_differing_targets','candidate_differing_targets','distance_difference_p95_max_m','complete_scan_semantics_qualified')} for r in d['pairs']],
  'common_orientation_summaries':d['common_orientation_summaries']})
p=suite/'declared_followup/status.json'
if p.exists():
 out['pipeline']=json.loads(p.read_text())
 if out['pipeline']['state']=='STOPPED_FOR_INSPECTION':
  log=suite/'declared_followup'/(out['pipeline']['active']+'_analysis.log')
  if log.is_file():out['analysis_tail']=log.read_text()[-2500:]
p=suite/'stage2_followup/status.json'
if p.exists():
 out['stage2_pipeline']=json.loads(p.read_text())
 if out['stage2_pipeline']['state']=='STOPPED_FOR_INSPECTION':
  log=suite/'stage2_followup'/(out['stage2_pipeline']['active']+'_analysis.log')
  if log.is_file():out['stage2_analysis_tail']=log.read_text()[-2500:]
print(json.dumps(out))
