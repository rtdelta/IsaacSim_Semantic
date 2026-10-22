"""Summarize saved measurements without changing raw data or primary classifications."""
import argparse,collections,json,math
from pathlib import Path
import numpy as np

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def read_rows(p):return [json.loads(s)['data'] for s in p.read_text(encoding='utf-8').splitlines()]
def quantiles(v):
    a=sorted(float(x) for x in v)
    return {str(q):a[max(0,math.ceil(q*len(a))-1)] for q in (.5,.95,.99,1.)} if a else None
def run(root,output):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    order=read(root/'frozen_config/run_order.json');records=[];data={}
    for phase in ('qualification','main','D_qualification','D_main'):
        for rel in order.get(phase,[]):
            spec=read(root/'frozen_config'/Path(rel).relative_to('config/native_instant_baseline'))
            parent=root/Path(spec['output_relative']).relative_to('reports/native_instant_baseline')
            if not (parent/'analysis/summary.json').exists():continue
            summary=read(parent/'analysis/summary.json');metrics=read(parent/'analysis/target_metrics.json');inc=read(parent/'analysis/adjacent_increments.json')
            associations=read(parent/'analysis/target_events.json');association_by_seq={a['receipt_seq']:a['physical_step'] for a in associations}
            raw=read_rows(parent/'continuous'/('raw_events.jsonl' if spec['group'].startswith('M') else 'raw_receipts.jsonl'))
            callback_lag=collections.Counter(r['callback_physical_step']-association_by_seq[r['receipt_seq']] for r in raw if association_by_seq[r['receipt_seq']] is not None)
            y=[m['geometry']['yaw_error_rad'] for m in metrics if m.get('geometry',{}).get('yaw_error_rad') is not None]
            dy=[m['geometry_increment_error_rad'] for m in inc if m['geometry_increment_error_rad'] is not None]
            r={'phase':phase,'group':spec['group'],'profile':spec['profile'],'repeat':spec['repeat'],'path':str(parent.relative_to(root)),
                **{k:summary[k] for k in ('planned_targets','planned_adjacent_pairs','measurement_qualified','cleanup_ok','diagnostic_pass','target_missing','target_duplicate','unassigned_events','native_pose_failed','geometry_absolute_failed','geometry_absolute_unknown','geometry_increment_failed','geometry_increment_unknown','candidate_counts','readback')},
                'candidate_status_counts':dict(collections.Counter(m.get('candidate',{}).get('status','unknown') for m in metrics)),
                'callback_delivery_lag_steps':dict(callback_lag),
                'ray_threshold_failed':sum(m.get('ray_residual_m',{}).get('0.95',0)>1e-5 for m in metrics),
                'plane_threshold_failed':sum(m.get('geometry',{}).get('point_plane_m',{}).get('0.95',0)>.005 for m in metrics),
                'yaw_threshold_failed':sum(abs(m['geometry']['yaw_error_rad'])>1e-4 for m in metrics if m.get('geometry',{}).get('yaw_error_rad') is not None),
                'absolute_yaw_error_rad':quantiles(abs(x) for x in y),'signed_yaw_error_rad':quantiles(y),'signed_yaw_min_rad':min(y) if y else None,
                'absolute_increment_error_rad':quantiles(abs(x) for x in dy),'first_target_yaw_error_rad':y[0] if y else None,
                'current_ray_p95_max_m':max((m['ray_residual_m']['0.95'] for m in metrics if 'ray_residual_m' in m),default=None),
                'plane_p95_max_m':max((m['geometry']['point_plane_m']['0.95'] for m in metrics if 'geometry' in m),default=None)}
            records.append(r);data[(phase,spec['group'],spec['profile'],spec['repeat'])]=(metrics,inc,parent)
    common=[]
    for group in ('M_E','P_E'):
        for repeat in ('r01','r02','r03'):
            ka=('main',group,'R3P',repeat);kb=('main',group,'R6P',repeat)
            if ka not in data or kb not in data:continue
            a,b=data[ka][0],data[kb][0];rows=[]
            for i in range(50):
                x,y=a[2*i+1],b[i]
                if abs(x['actual_yaw_rad']-y['actual_yaw_rad'])>1e-6:raise ValueError('Predeclared common orientation inputs disagree')
                rows.append({'yaw_deg':math.degrees(x['actual_yaw_rad']),'R3P_candidate':x['candidate']['best_members'],'R6P_candidate':y['candidate']['best_members'],
                    'R3P_lag_steps':x['descriptive_equivalent_lag_steps'],'R6P_lag_steps':y['descriptive_equivalent_lag_steps'],
                    'R3P_signed_error_rad':x['geometry']['yaw_error_rad'],'R6P_signed_error_rad':y['geometry']['yaw_error_rad']})
            common.append({'group':group,'repeat':repeat,'targets':50,'candidate_different':sum(r['R3P_candidate']!=r['R6P_candidate'] for r in rows),'rows':rows})
    comparison={phase:read(root/order['experiment_id']/(phase+'_comparison.json')) for phase in ('qualification','main','D_qualification','D_main') if (root/order['experiment_id']/(phase+'_comparison.json')).exists()}
    result={'records':records,'common_orientation_comparison':common,'comparisons':comparison,'formal_continuous_acceptance':False,'payload_generation_freshness':None}
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    lines=['| 阶段 | 组别 | 条件 | 重复 | 原生姿态失败/N | 绝对几何失败/N | 相邻增量失败/(N−1) | 候选计数 |','|---|---|---|---|---:|---:|---:|---|']
    for r in records:
        lines.append('| {phase} | {group} | {profile} | {repeat} | {native_pose_failed}/{planned_targets} | {geometry_absolute_failed}/{planned_targets} | {geometry_increment_failed}/{planned_adjacent_pairs} | {candidate_counts} |'.format(**r))
    (output/'run_table.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'runs':len(records),'all_measurement_qualified':all(r['measurement_qualified'] for r in records),'all_cleanup_ok':all(r['cleanup_ok'] for r in records),
        'phase_counts':dict(collections.Counter(r['phase'] for r in records)),'pair_qualified':{k:v['all_measurement_and_pair_qualified'] for k,v in comparison.items()}}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('output');a=p.parse_args();run(a.root,a.output)
