"""Collect every failure of the fixed header-midpoint model from verified delivery."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'reports/native007_delivery_20261015';E=BASE/'evidence';rows=[];sources=[]
for p in sorted((E/'stage_analysis').glob('*/header_*.json')):
 d=json.loads(p.read_text());bad=[x for x in d['targets'] if x['header_midpoint_distance_p95_m']>1e-5]
 sources.append({'path':p.relative_to(BASE).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 if bad:rows.append({'stage':p.parent.name,'run':d['run'],'counterexamples':bad})
out=BASE/'derived';out.mkdir(exist_ok=True)
result={'scope':'All fixed reported-header-midpoint model failures, all analyzed stages; derived from verified local delivery, no threshold changes or exclusions','source_files':sources,'runs_with_counterexamples':rows,'total_counterexamples':sum(len(r['counterexamples']) for r in rows)}
(out/'all_header_midpoint_counterexamples.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'total_counterexamples':result['total_counterexamples'],'runs':[{ 'stage':r['stage'],'run':r['run'],'targets':[{'target_index':x['target_index'],'motion_step':x['motion_step'],'residual_m':x['header_midpoint_distance_p95_m'],'candidate':x['distance_candidate']['best_members']} for x in r['counterexamples']]} for r in rows]}))
