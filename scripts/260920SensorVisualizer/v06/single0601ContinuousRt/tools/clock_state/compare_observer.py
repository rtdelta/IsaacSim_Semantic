"""Per-target T0 comparisons; never pool repeated frames as independent runs."""
import json,sys
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tools.experiments.storage import rows,save
from single0601_continuous_rt.sensor_backend import pose_error


def compare(a,b):
    def load(p):
        return {'metrics':json.loads((p/'analysis/planned_target_metrics.json').read_text()),'summary':json.loads((p/'analysis/summary.json').read_text()),
            'targets':{r['target_index']:r for r in rows(p/'continuous/targets.jsonl')},'updates':rows(p/'continuous/app_updates.jsonl')}
    aa,bb=load(a),load(b);errors=[];differences=[]
    for index in sorted(set(aa['targets']) & set(bb['targets'])):
        p,r=pose_error(aa['targets'][index]['actual_state']['sensor_world_matrices_usd']['lidar/MyAiry_front'],bb['targets'][index]['actual_state']['sensor_world_matrices_usd']['lidar/MyAiry_front']);errors.append((p,r))
        x,y=aa['metrics'][index],bb['metrics'][index]
        if any(x[k]!=y[k] for k in ('clock_mapping_ok','native_pose_ok','geometry_ok')):differences.append(index)
    return {'A':str(a),'B':str(b),'same_target_count':len(aa['targets'])==len(bb['targets']),
        'max_actual_input_translation_m':max((p for p,r in errors),default=None),'max_actual_input_rotation_rad':max((r for p,r in errors),default=None),
        'target_failure_class_different_indices':differences,'A_native_pose_failed':aa['summary']['native_pose_failed'],'B_native_pose_failed':bb['summary']['native_pose_failed'],
        'A_geometry_failed':aa['summary']['geometry_failed'],'B_geometry_failed':bb['summary']['geometry_failed'],
        'A_app_update_wall_median_s':float(np.median([(int(u['finished_monotonic_ns'])-int(u['started_monotonic_ns']))/1e9 for u in aa['updates']])),
        'B_app_update_wall_median_s':float(np.median([(int(u['finished_monotonic_ns'])-int(u['started_monotonic_ns']))/1e9 for u in bb['updates']])),
        'scope':'input-qualified paired diagnostic observer effect; CPU phase order not observed in A, no GPU execution claim'}


if __name__=='__main__':
    result=compare(Path(sys.argv[1]),Path(sys.argv[2]));save(Path(sys.argv[3]),result);print(json.dumps(result))
