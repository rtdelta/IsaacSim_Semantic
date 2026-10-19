import json
from pathlib import Path
root=Path(__file__).resolve().parents[2];base=root/'reports/remote/reports/clock_state_consistency/clock_20261014_v2'
results=[]
for condition in ('T5_PRE_qualification','T6_HOLD2_WRITE_qualification'):
    parent=base/condition/'repeats/r01'
    if not (parent/'analysis_local_readback/summary.json').exists():continue
    def read(folder,name):return json.loads((parent/folder/(name+'.json')).read_text(encoding='utf-8'))
    remote=read('analysis_provenance_gate','summary');local=read('analysis_local_readback','summary')
    keys=['measurement_qualified','target_provenance_qualified','failure_crosstable','native_pose_failed','geometry_failed',
        'geometry_plane_failed','best_candidate_group_counts','all_GMO_valid_XYZ_equals_extractor','full_gmo_analyzed']
    same_summary=all(remote[k]==local[k] for k in keys)
    a,b=read('analysis_provenance_gate','planned_target_metrics'),read('analysis_local_readback','planned_target_metrics')
    same_target=len(a)==len(b) and all(all(x[k]==y[k] for k in ('target_index','joint_cell','input_qualified','event_provenance_ok')) for x,y in zip(a,b))
    a,b=read('analysis_provenance_gate','component_delay'),read('analysis_local_readback','component_delay')
    same_candidates=len(a)==len(b) and all(all(x[k]==y[k] for k in ('target_index','status','best_members','position_lag_steps','rotation_lag_steps')) for x,y in zip(a,b))
    result={'condition':condition,'summary_decisions_equal':same_summary,'all_target_decisions_equal':same_target,
        'all_candidate_decisions_equal':same_candidates,'local_original_evidence_files_SHA_verified':local['verified_files'],
        'full_GMO_independently_decoded':local['full_gmo_analyzed'],
        'plane_max_statistic_delta_m':abs(local['C_max_plane_p95_m']-remote['C_max_plane_p95_m']),
        'yaw_max_statistic_delta_rad':abs(local['C_max_abs_yaw_rad']-remote['C_max_abs_yaw_rad'])}
    if not all((same_summary,same_target,same_candidates)):raise ValueError('Local readback decisions differ '+condition)
    results.append(result)
out={'schema_version':1,'scope':'Windows CPU reanalysis of audited complete native evidence pairs; no SDK simulation on local machine','runs':results}
(root/'reports/clock_local_raw_reanalysis_20261014.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out))
