"""Final inventory keeps every completed, failed and unstarted locked condition."""
import collections,datetime,hashlib,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
evidence=root/'reports/clock_state_consistency'
out={'schema_version':1,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runs':[],'condition_inventory':[],
    'formal_continuous_acceptance':False,'payload_freshness_ok':None}
for p in sorted(evidence.glob('clock_20261014_v*/**/experiment_spec.json')):
    # Continuous/frozen copies are not separate runs.
    if p.parent.parent.name!='repeats':continue
    parent=p.parent;spec=json.loads(p.read_text());analysis=parent/'analysis/summary.json'
    status=json.loads((parent/'coordinator_status.json').read_text()) if (parent/'coordinator_status.json').exists() else {}
    row={'path':parent.relative_to(root).as_posix(),'condition':spec['condition'],'repeat':spec['repeat'],'planned_targets':spec['targets'],
        'state':status.get('state'),'spec_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    for side in ('continuous','frozen_room'):
        terminal=parent/('continuous_terminal.json' if side=='continuous' else 'frozen_terminal.json')
        if terminal.exists():
            end=json.loads(terminal.read_text());row[side+'_terminal_status']=end.get('status');row[side+'_cleanup_passed']=end.get('cleanup',{}).get('passed')
        manifest=parent/side/'file_manifest.json'
        if manifest.exists():
            d=json.loads(manifest.read_text());row[side+'_evidence_bytes']=sum(x['bytes'] for x in d['files'])
            row[side+'_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if analysis.exists():
        s=json.loads(analysis.read_text());row.update({k:s.get(k) for k in (
            'measurement_qualified','native_pose_failed','geometry_failed','geometry_plane_failed','C_max_plane_p95_m','C_max_abs_yaw_rad',
            'frozen_max_ray_p95_m','raw_event_count','unassigned_event_count','rejected_event_count','full_gmo_analyzed',
            'all_GMO_valid_XYZ_equals_extractor','clock_mapping_ok','event_provenance_ok','failure_crosstable','best_candidate_group_counts')})
    row['lifecycle_qualified']=row.get('continuous_cleanup_passed') is True and row.get('frozen_room_cleanup_passed') is True
    row['run_qualified']=row.get('measurement_qualified') is True and row['lifecycle_qualified']
    out['runs'].append(row)
for p in sorted((root/'config/clock_state').glob('*.json')):
    s=json.loads(p.read_text())
    if s.get('suite')!='clock_state_v1':continue
    parent=evidence/s['experiment_id']/s['condition']/'repeats'/s['repeat']
    status=parent/'coordinator_status.json'
    out['condition_inventory'].append({'spec':p.relative_to(root).as_posix(),'experiment_id':s['experiment_id'],
        'condition':s['condition'],'repeat':s['repeat'],'targets':s['targets'],
        'status':json.loads(status.read_text()).get('state') if status.exists() else 'not_run'})
out['totals']={'executed_pairs':len(out['runs']),'completed_pairs':sum(r['state']=='COMPLETE' for r in out['runs']),
    'measurement_qualified_pairs':sum(r.get('measurement_qualified') is True for r in out['runs']),
    'run_qualified_pairs':sum(r['run_qualified'] for r in out['runs']),
    'planned_targets_per_side':sum(r['planned_targets'] for r in out['runs']),
    'full_gmo_analyzed':sum(r.get('full_gmo_analyzed',0) for r in out['runs']),
    'evidence_bytes':sum(r.get(side+'_evidence_bytes',0) for r in out['runs'] for side in ('continuous','frozen_room')),
    'both_sides_cleanup_passed_pairs':sum(r.get('continuous_cleanup_passed') is True and r.get('frozen_room_cleanup_passed') is True for r in out['runs']),
    'not_run_specs':sum(r['status']=='not_run' for r in out['condition_inventory'])}
(evidence/'execution_inventory.json').write_text(json.dumps(out,indent=2))
print(json.dumps({'totals':out['totals'],'noncomplete':[r for r in out['runs'] if r['state']!='COMPLETE'],
    'cleanup_not_confirmed':[r for r in out['runs'] if r.get('continuous_cleanup_passed') is not True or r.get('frozen_room_cleanup_passed') is not True],
    'not_run':[r for r in out['condition_inventory'] if r['status']=='not_run']}))
