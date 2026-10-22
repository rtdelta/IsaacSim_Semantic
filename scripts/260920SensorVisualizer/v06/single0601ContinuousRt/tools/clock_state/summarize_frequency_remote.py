"""Read-only measurements; derived frequency report uses predeclared angle sets."""
import collections,itertools,json,math
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/clock_state_consistency/clock_20261014_v1')
conditions=('T2_Rplus','T4_B120_3','T4_C120_6','T4_D60_6')
result={'schema_version':1,'conditions':[],'matched_comparisons':[],
    'interpretation':'Descriptive per independent run. No pooling targets as independent repeats. Equivalent seconds only in constant nonzero rotation. CPU actual quaternion is not GPU history.'}
available={}
def rows(path):return [json.loads(line)['data'] for line in path.read_text().splitlines() if line.strip()]
def counts(items):return dict(collections.Counter(str(x) for x in items))
def aggregate(selected):
    return {'targets':len(selected),'native_pose_failed':sum(x['native_pose_ok'] is False for x in selected),
        'geometry_failed':sum(x['geometry_ok'] is False for x in selected),
        'plane_failed':sum(x['plane_p95_m']>.005 for x in selected),'lag_steps_counts':counts(x['lag_steps'] for x in selected),
        'lag_seconds_counts':counts(x['lag_s'] for x in selected),'max_abs_yaw_rad':max((abs(x['yaw_fit_rad']) for x in selected),default=None),
        'max_plane_p95_m':max((x['plane_p95_m'] for x in selected),default=None)}
for condition,repeat in itertools.product(conditions,('r01','r02','r03')):
    parent=root/condition/'repeats'/repeat
    if not (parent/'analysis/summary.json').exists():continue
    summary=json.loads((parent/'analysis/summary.json').read_text());spec=json.loads((parent/'experiment_spec.json').read_text())
    if spec['targets']!=100:continue
    targets={r['target_index']:r for r in rows(parent/'continuous/targets.jsonl')}
    metrics=json.loads((parent/'analysis/planned_target_metrics.json').read_text())
    components={r['target_index']:r for r in json.loads((parent/'analysis/component_delay.json').read_text())}
    allrows=[]
    for m in metrics:
        i=m['target_index'];q=targets[i]['actual_state']['root']['orientation_xyzw']
        actual=math.degrees(2*math.atan2(q[2],q[3]))-spec.get('initial_yaw_deg',0)
        nominal=(i+1)*spec['yaw_rate_deg_s']/10
        if abs(actual-nominal)>math.degrees(1e-6):raise ValueError('Actual orientation deviates from declared strata')
        c=components[i];lag=c['rotation_lag_steps'][0] if c['rotation_delay_identifiable'] and len(c['rotation_lag_steps'] or [])==1 else None
        geo=m['C_geometry']
        allrows.append({'target_index':i,'relative_yaw_deg':actual,'nominal_yaw_deg':nominal,
            'lag_steps':lag,'lag_s':lag/spec['physics_hz'] if lag is not None else None,
            'yaw_fit_rad':geo['yaw_fit_rad'],'abs_yaw_equivalent_delay_s':abs(geo['yaw_fit_rad'])/abs(math.radians(spec['yaw_rate_deg_s'])),
            'plane_p95_m':geo['point_plane_m']['0.95'],'native_pose_ok':m['native_pose_ok'],'geometry_ok':m['geometry_ok']})
    common=[allrows[i] for i in spec['orientation_strata']['target_indices']]
    match=spec['common_orientation_match_06deg'];matched=[allrows[i] for i in match['target_indices']]
    if any(abs(x['relative_yaw_deg']-angle)>math.degrees(1e-6) for x,angle in zip(matched,match['angles_deg'])):raise ValueError('Matched orientation not equal')
    bins=[]
    for index in range(30):
        group=[x for x in common if min(29,int(math.floor(x['nominal_yaw_deg']+1e-10)))==index]
        bins.append(dict(bin_degrees=[index,index+1],**aggregate(group)))
    row={'condition':condition,'repeat':repeat,'physics_hz':spec['physics_hz'],'angular_speed_deg_s':spec['yaw_rate_deg_s'],
        'per_step_angle_deg':spec['yaw_rate_deg_s']/spec['physics_hz'],'measurement_qualified':summary['measurement_qualified'],
        'all_targets':aggregate(allrows),'common_0_30_degrees':aggregate(common),'matched_50_orientations':aggregate(matched),
        'one_degree_bins':bins,'per_target':allrows,'frozen_max_ray_p95_m':summary['frozen_max_ray_p95_m']}
    result['conditions'].append(row);available[condition,repeat]=matched
for repeat in ('r01','r02','r03'):
    for a,b in itertools.combinations(conditions,2):
        if (a,repeat) not in available or (b,repeat) not in available:continue
        x,y=available[a,repeat],available[b,repeat]
        result['matched_comparisons'].append({'conditions':[a,b],'repeat':repeat,'targets':len(x),
            'lag_steps_equal':sum(p['lag_steps']==q['lag_steps'] for p,q in zip(x,y)),
            'lag_seconds_equal':sum(p['lag_s']==q['lag_s'] for p,q in zip(x,y)),
            'max_abs_actual_orientation_difference_deg':max(abs(p['relative_yaw_deg']-q['relative_yaw_deg']) for p,q in zip(x,y)),
            'lag_steps_different_angle_degrees':[p['nominal_yaw_deg'] for p,q in zip(x,y) if p['lag_steps']!=q['lag_steps']]})
(root/'frequency_comparison.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'conditions':[{k:v for k,v in r.items() if k not in ('one_degree_bins','per_target')} for r in result['conditions']],
    'matched_comparisons':result['matched_comparisons']}))
