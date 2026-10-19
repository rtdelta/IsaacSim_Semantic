"""Summarize locally verified real native trials; never promotes formal READY."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0601_continuous_rt.common import file_hash,save_json,utc


def summarize():
    directory=ROOT/'reports/remote/reports/recovery_delivery_evidence'
    manifest_path=directory/'evidence_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    for entry in manifest['files']:
        path=(directory/entry['path']).resolve()
        if directory.resolve() not in path.parents or not path.is_file():raise ValueError('Missing or out-of-scope evidence')
        if path.stat().st_size!=entry['bytes'] or file_hash(path)!=entry['sha256']:raise ValueError('Evidence transfer integrity mismatch')
    frozen=json.loads((directory/'recovery_native_runs.json').read_text(encoding='utf-8'))
    trials=[]
    for run in frozen['runs']:
        report=run['report'];native=run.get('native_analysis.json',{});geometry=run.get('room_geometry_analysis.json');rotation=run.get('room_rotation_analysis.json')
        trials.append({'run_id':run['run_id'],'status':report['status'],'scene':report.get('scene_mode','scene18; legacy probe did not record scene_mode'),
            'profile':report['profile'],'motion':report['motion'],'sensor_pose_mode':report.get('sensor_pose_mode','mounted'),
            'motion_history':report.get('motion_history','default'),'tlas':report.get('tlas','sensor'),
            'effective_settings':report.get('effective_settings',{}),'counts':report.get('counts',{}),
            'pose_bad_rows':report.get('pose_bad_rows'),'cleanup_passed':report['cleanup'].get('passed'),
            'trace_bytes':report['trace_bytes'],'native_analysis':native,'geometry_analysis':geometry,'rotation_analysis':rotation,
            'failure':report.get('failure'),'evidence_path':str((directory/run['run_id']).relative_to(ROOT)).replace('\\','/')})
    finished=[t for t in trials if t['status']=='diagnostic_completed']
    result={'schema_version':1,'created_utc':utc(),'scope':'004 C0/C1 implementation and bounded C2 diagnostic outcomes; no continuous formal recording',
        'evidence_manifest_sha256':file_hash(manifest_path),'verified_evidence_files':len(manifest['files']),
        'trials':trials,'completed_trials':len(finished),'failed_trials':len(trials)-len(finished),
        'completed_native_receipts':sum(sum(t['counts'].values()) for t in finished),
        'continuous_ok':False,'formal_continuous_recordings_created':0,'new_ready_created':0,
        'mechanism_route':'R5 reproducible current-runtime problem; no verified project-level repair',
        'proven_findings':['Low-angle continuous rotation produces both native pose and independently measured ray errors',
            'Current Fabric world matrices match actual USD matrices at observed phases',
            'Owned packed GMO headers match installed-parser scalar metadata independently',
            'Zero-delay, actual-driven render rig, and per-frame TLAS contrasts did not meet the continuous gate'],
        'candidate_cause':'Small-angle transform-history interpolation in the native rendering/sensor chain; exact function and defect not established',
        'evidence_limits':['No installed public transform-history reader verified',
            'GMO point timestamp anchor and Instant single-time semantics remain unverified',
            'No valid resume payload acceptance in this diagnostic; physical-clock pause is the tested property',
            'Full C2 three-initialization trajectory matrix, other lidar models, and nonuniform motion were not completed',
            'Scene18 independent continuous-ray geometry, quality comparison, and VRAM/long-run budgets remain unverified'],
        'stages':{'C0':'diagnostic baseline frozen; formal long-run budgets pending','C1':'native event/phase/owned-byte observation implemented with documented interface gaps',
            'C2':'bounded hypotheses evaluated and minimal reproducer retained; repair gate failed',
            'C3':'not entered','C4':'not entered','C5':'not entered','C6':'not entered'},
        'prior_barrier_results':'36 root READY recordings / 1612 previously read-back groups; no acceptance inherited by continuous',
        'preservation':json.loads((ROOT/'reports/recovery_final_preservation_actual.json').read_text(encoding='utf-8')),
        'logic_tests':json.loads((ROOT/'reports/logic_tests.json').read_text(encoding='utf-8')),
        'source_integrity':json.loads((ROOT/'reports/source_integrity.json').read_text(encoding='utf-8'))}
    save_json(ROOT/'reports/continuous_recovery_result.json',result)
    prior=json.loads((ROOT/'reports/project_acceptance.json').read_text(encoding='utf-8'))
    acceptance=dict(prior,scope='Project acceptance against plans 002/003/004, 2026-10-14; barrier results retain prior readback scope',
        full_delivery=False,report_path='../docs/Execution/20261014_execution.md',
        recovery_evidence_path='continuous_recovery_result.json',
        completed_native_diagnostic_trials=len(finished),formal_continuous_recordings_created=0,
        current_originals_preserved=result['source_integrity']['original_preservation']['passed'],
        current_ready_manifests_preserved=result['preservation']['ready_same_as_c0'])
    save_json(ROOT/'reports/project_acceptance_20261014.json',acceptance)
    print(json.dumps({k:result[k] for k in ('completed_trials','failed_trials','completed_native_receipts','verified_evidence_files','continuous_ok','mechanism_route')}))


if __name__=='__main__':summarize()
