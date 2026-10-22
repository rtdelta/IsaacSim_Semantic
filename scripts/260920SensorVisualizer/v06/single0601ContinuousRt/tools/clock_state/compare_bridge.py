import json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tools.experiments.storage import rows,save
from single0601_continuous_rt.sensor_backend import pose_error
from tools.clock_state.compare_observer import compare
base=PROJECT/'reports/clock_state_consistency/clock_20261014_v1'
a=base/'qualification_legacy_incremental/repeats/r01';b=base/'qualification_legacy_table/repeats/r01'
old=PROJECT/'reports/paired_capture_experiments/paired_20261014_e2_room_mixed/repeats/r01'
report={'schema_version':1,'incremental_vs_table':compare(a,b),'old_baseline':str(old),'baseline_comparisons':{}}
original_targets=rows(old/'continuous/targets.jsonl')[:12]
original_metrics=[json.loads(line) for line in (old/'analysis/paired_metrics.jsonl').read_text().splitlines()][:12]
for name,path in [('incremental',a),('table',b)]:
    targets=rows(path/'continuous/targets.jsonl');metrics=json.loads((path/'analysis/planned_target_metrics.json').read_text());pe=[];re=[]
    for current,previous in zip(targets,original_targets):
        p,r=pose_error(current['actual_state']['sensor_world_matrices_usd']['lidar/MyAiry_front'],previous['actual_state']['sensor_world_matrices_usd']['lidar/MyAiry_front']);pe.append(p);re.append(r)
    report['baseline_comparisons'][name]={'targets':len(targets),'max_actual_position_error_m':max(pe),'max_actual_rotation_error_rad':max(re),
        'input_qualified':all(p<=1e-5 for p in pe) and all(r<=1e-6 for r in re),
        'native_failure_indices_equal':all(x['native_pose_ok']==y['C_native_pose_pass'] for x,y in zip(metrics,original_metrics))}
save(base/'legacy_bridge_comparison.json',report);print(json.dumps(report))
