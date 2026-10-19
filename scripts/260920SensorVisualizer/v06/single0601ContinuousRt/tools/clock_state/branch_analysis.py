"""Actual-state paired comparisons, HOLD observations and measured costs."""
import itertools,json,sys
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tools.experiments.storage import rows,save
from tools.clock_state.compare_observer import compare
from single0601_continuous_rt.sensor_backend import pose_error

def analyze(root):
    root=Path(root);out={'schema_version':1,'runs':[],'comparisons':[],
        'freshness':'unknown: new event headers do not independently prove payload recomputation',
        'trajectory_scope':'mechanism only; unaltered increments per moving step, different average paths across hold modes'}
    parents={}
    for p in sorted(root.glob('*/repeats/*')):
        if not (p/'analysis/summary.json').exists():continue
        s=json.loads((p/'analysis/summary.json').read_text());spec=s['spec'];c=p/'continuous'
        updates=rows(c/'app_updates.jsonl');motion=[u for u in updates if u['phase']=='motion_and_drain']
        span=(int(motion[-1]['finished_monotonic_ns'])-int(motion[0]['started_monotonic_ns']))/1e9
        trace=rows(c/'actual_states.jsonl');table=rows(c/'target_pose_table.jsonl');by_step={s['physical_step']:s for s in trace}
        selected=[by_step[t['physical_step']] for t in table if t['physical_step'] in by_step]
        distance=sum(float(np.linalg.norm(np.asarray(b['root']['position_m'])-a['root']['position_m'])) for a,b in zip(selected,selected[1:]))
        sim_span=(int(selected[-1]['sim_time_ns'])-int(selected[0]['sim_time_ns']))/1e9
        writes=rows(c/'pose_writes.jsonl')+rows(c/'post_pose_writes.jsonl');held=rows(c/'hold_actual_states.jsonl')
        manifest=json.loads((c/'file_manifest.json').read_text());fs=json.loads((p/'frozen_room/file_manifest.json').read_text())
        metrics=json.loads((p/'analysis/planned_target_metrics.json').read_text())
        passing=sum(m['clock_mapping_ok'] is True and m['native_pose_ok'] is True and m['geometry_ok'] is True for m in metrics)
        parents[spec['condition'],spec['repeat']]=p
        out['runs'].append({'condition':spec['condition'],'repeat':spec['repeat'],'targets':spec['targets'],
            'measurement_qualified':s['measurement_qualified'],'native_pose_failed':s['native_pose_failed'],'geometry_failed':s['geometry_failed'],
            'plane_failed':s['geometry_plane_failed'],'C_max_plane_p95_m':s['C_max_plane_p95_m'],'C_max_abs_yaw_rad':s['C_max_abs_yaw_rad'],
            'best_candidate_group_counts':s['best_candidate_group_counts'],'candidate_status_counts':s['candidate_status_counts'],
            'source_mapping_ok':s['clock_mapping_ok'],'provenance_ok':s['event_provenance_ok'],'payload_freshness_ok':None,
            'held_actual_observations':len(held),'all_held_inputs_qualified':all(h['input_qualified'] for h in held) if held else None,
            'motion_table_API_writes':sum(bool(w.get('authored')) for w in writes),
            'motion_table_skipped_PRE_writes':sum(w.get('authored') is False for w in writes),
            'motion_and_drain_wall_s':span,'motion_and_drain_sim_s':sim_span,'measured_path_m':distance,
            'path_m_per_sim_s':distance/sim_span,'path_m_per_wall_s':distance/span,
            'three_axis_passing_targets':passing,'three_axis_passing_targets_per_motion_wall_s':passing/span,
            'cost_scope':'active motion plus planned drain; excludes Kit initialization/F replay; not full accepted production throughput',
            'C_queue_peak_bytes':manifest['queue_peak_bytes'],'C_written_bytes':manifest['written_bytes'],'F_written_bytes':fs['written_bytes'],
            'C_reserved_uncompressed_bytes':manifest['reserved_disk_bytes'],'F_reserved_uncompressed_bytes':fs['reserved_disk_bytes']})
    for suffix,repeat in itertools.product(('_qualification',''),('r01','r02','r03')):
        for a,b in [('T5_PRE','T5_POST'),('T6_HOLD2_WRITE','T6_HOLD2_SKIP'),('T6_ALT_WRITE','T6_ALT_SKIP')]:
            keya,keyb=(a+suffix,repeat),(b+suffix,repeat)
            if keya not in parents or keyb not in parents:continue
            pa,pb=parents[keya],parents[keyb];comparison=compare(pa,pb)
            aa={r['physical_step']:r for r in rows(pa/'continuous/actual_states.jsonl')};bb={r['physical_step']:r for r in rows(pb/'continuous/actual_states.jsonl')}
            errors=[pose_error(aa[k]['sensor_world_matrices_usd']['lidar/MyAiry_front'],bb[k]['sensor_world_matrices_usd']['lidar/MyAiry_front']) for k in aa.keys()&bb.keys()]
            comparison.update(scope='Same recorder and condition family, actual all-step and target equivalence. No GPU order claim.',
                same_actual_step_keys=set(aa)==set(bb),actual_steps_compared=len(errors),
                all_step_max_translation_m=max(e[0] for e in errors),all_step_max_rotation_rad=max(e[1] for e in errors))
            out['comparisons'].append(comparison)
    save(root/'branch_comparison.json',out)
    print(json.dumps(out));return out

if __name__=='__main__':analyze(sys.argv[1])
