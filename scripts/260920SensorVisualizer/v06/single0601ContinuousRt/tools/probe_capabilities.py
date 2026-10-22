"""M0 real moving-payload capability probe, run inside the project-owned Kit."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


async def run():
    import omni.kit.app
    from single0601_continuous_rt.common import save_json, file_hash, utc
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.engine_owner import EngineOwner
    from single0601_continuous_rt.sensor_backend import pose_error
    output = PROJECT / 'reports' / ('probe_' + time.strftime('%Y%m%d_%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    owner = EngineOwner(PROJECT, load(os.environ['S0601_JOB']))
    owner.moving = True
    rows, errors, first_owned = [], [], {}
    expected, tick_sets, duplicates = set(), {}, {}
    warmup = 0
    phase = 'initializing'
    def received(evidence, owned):
        sid = evidence['sensor_id']
        try:
            step, state = owner.ledger.exact_time(owner.epoch_id, int(evidence['source_time_ns']))
            historical = state['sensor_world_matrices_usd'][sid]
            translation, angle = pose_error(historical, evidence['rendered_to_world'])
            row = dict(evidence, phase=phase, physical_step=step, state_time_ns=state['sim_time_ns'],
                       state_revision=state['state_revision'], historical_to_world=historical,
                       translation_error_m=translation, rotation_error_rad=angle,
                       snapshot_monotonic_ns=state['snapshot_monotonic_ns'])
            rows.append(row)
            tick_sets.setdefault(sid, set()).add(int(evidence['source_time_ns']))
            if sid not in first_owned:
                first_owned[sid] = (owned, hashlib.sha256(owned.tobytes()).hexdigest())
        except Exception as exc:
            errors.append({'code': getattr(exc, 'code', 'probe_state'), 'sensor_id': sid, 'phase':phase,
                           'message': str(exc), 'evidence': evidence})
    owner.on_receipt = received
    def rejected(error):
        errors.append(dict(error, phase=phase))
    owner.on_reject = rejected
    report = {'schema_version': 1, 'recording_id': owner.recording_id, 'capability_id': owner.capability_id,
              'status': 'unsupported', 'selected_backend': None, 'tests': [], 'source_mapping': {},
              'state_capture_phase': 'PHYSICS_PRE_STEP order=-100 integrates physical dt once and applies prescribed state; PHYSICS_POST_STEP order=100 reads actual state before Hydra',
              'failures': []}
    try:
        await owner.initialize()
        expected = {e['sensor_id'] for k in ('cameras','lidars') for e in owner.registry[k]}
        save_json(output/'environment.json', owner.environment())
        save_json(output/'sensor_registry.json', owner.registry)
        save_json(output/'render_profile.json', owner.render_profile)
        save_json(output/'job_spec.json', owner.job)
        save_json(output/'asset_manifest.json', owner.asset_manifest())
        files = [{'path': p.relative_to(PROJECT).as_posix(), 'sha256': file_hash(p), 'size_bytes': p.stat().st_size,
                  'origin_path': None, 'modified': False} for p in PROJECT.rglob('*.py') if '__pycache__' not in p.parts]
        save_json(output/'source_manifest.json', {'schema_version': 1, 'recording_id': owner.recording_id,
                    'entrypoint': 'tools/probe_capabilities.py', 'files': files, 'git': None})
        owner.timeline.play()
        owner.timeline.commit()
        phase = 'continuous'
        for warmup in range(1, owner.job['render']['initial_warmup_max_updates'] + 1):
            await owner.app.next_update_async()
            if owner.error:
                raise RuntimeError(str(owner.error))
            if warmup >= owner.job['render']['initial_warmup_min_updates'] and all(tick_sets.get(sid) for sid in expected):
                break
        else:
            raise RuntimeError('No complete selected-sensor tick in bounded initialization')
        for _ in range(300):
            if all(len(tick_sets.get(sid, ())) >= 24 for sid in expected):
                break
            await owner.app.next_update_async()
            if owner.error:
                raise RuntimeError(str(owner.error))
        pre_pause_time = owner.manager.get_simulation_time()
        phase = 'paused_diagnostic'
        owner.setting('/app/player/playSimulations', False)
        for _ in range(10):
            await owner.app.next_update_async()
        paused_time = owner.manager.get_simulation_time()
        owner.setting('/app/player/playSimulations', True)
        phase = 'resuming_diagnostic'
        for _ in range(30):
            await owner.app.next_update_async()
        import numpy as np
        tests = []
        def test(name, passed, reason, count):
            tests.append({'name': name, 'passed': bool(passed), 'reason': reason,
                          'evidence_paths': ['probe_receipts.json', 'probe_errors.json'], 'sample_count': count})
        test('writer_capture_on_play', all(len(tick_sets.get(s, ())) >= 20 for s in expected), 'Same-event Writer payloads while Timeline plays', len(rows))
        continuous_errors = [e for e in errors if e.get('phase') == 'continuous']
        test('source_time_reference_mapping', bool(rows) and not continuous_errors, 'Playing moving payloads cross-checked against get_simulation_time_at_time(ReferenceTime); paused cached callbacks separately rejected', len(rows))
        test('rendered_pose_matches_actual_history', bool(rows) and all(r['translation_error_m'] <= .001 and r['rotation_error_rad'] <= .0001 for r in rows), 'Independent native rendered transform compared to pre-render actual state', len(rows))
        test('owned_cpu_lifetime', bool(first_owned) and all(hashlib.sha256(array.tobytes()).hexdigest() == h for array, h in first_owned.values()), 'do_array_copy=True plus immediate independent C-contiguous CPU copy; retained copies unchanged after later native renders', len(first_owned))
        common = set.intersection(*(tick_sets.get(s, set()) for s in sorted(expected))) if expected else set()
        spacing = [b-a for a,b in zip(sorted(common), sorted(common)[1:])]
        test('common_tick_frequency_and_phase', len(common) >= 20 and all(abs(dt-100000000) <= 2 for dt in spacing), 'Selected native ticks share the same physical 10 Hz grid', len(common))
        distinct_poses = {s: len({json.dumps(r['historical_to_world']) for r in rows if r['sensor_id'] == s}) for s in expected}
        test('moving_state_capture_phase', all(n >= 20 for n in distinct_poses.values()), 'At least 20 distinct moving actual poses per selected sensor', min(distinct_poses.values(), default=0))
        test('pause_resume', pre_pause_time == paused_time and owner.manager.get_simulation_time() > paused_time,
             'Safe-boundary physics suspension: physical time frozen during ten updates while native generation retained, then resumed without reset', 40)
        report['tests'] = tests
        report['warmup_updates'] = warmup
        report['observed_native_tick_count'] = {s: len(tick_sets.get(s, ())) for s in expected}
        report['common_tick_count'] = len(common)
        report['distinct_moving_poses'] = distinct_poses
        report['max_native_lead_groups'] = None
        # Multi-flight remains unverified until safe-boundary lead and credit tests.
        for sid in expected:
            report['source_mapping'][sid] = {'annotator': 'IsaacReadSimulationTime', 'clock_domain': 'physics_simulation',
                'mapping_method': 'get_simulation_time_at_time(ReferenceTime)', 'native_ref_kind': 'rational_time',
                'native_ref_scope': next((r['native_ref']['scope'] for r in rows if r['sensor_id']==sid), sid),
                'max_native_lead_groups': None, 'verified_max_inflight': 1}
        if all(t['passed'] for t in tests):
            report.update(status='continuous_verified', selected_backend='continuous')
        else:
            report['failures'] += [{'code': t['name'], 'message': t['reason'], 'evidence_paths': t['evidence_paths']} for t in tests if not t['passed']]
    except Exception as exc:
        errors.append({'code': getattr(exc, 'code', 'probe_failed'), 'message': str(exc), 'traceback': traceback.format_exc()})
        report['failures'].append({'code': getattr(exc, 'code', 'probe_failed'), 'message': str(exc), 'evidence_paths': ['probe_errors.json']})
    finally:
        phase = 'cleanup'
        save_json(output/'probe_receipts.json', rows)
        save_json(output/'probe_errors.json', errors)
        try:
            await owner.close()
            report['cleanup_succeeded'] = True
        except Exception as exc:
            report['cleanup_succeeded'] = False
            report.update(status='unsupported', selected_backend=None)
            report['failures'].append({'code': 'cleanup_failed', 'message': type(exc).__name__+': '+str(exc), 'evidence_paths': []})
        save_json(output/'capabilities.json', report)
        save_json(PROJECT/'reports/latest_probe.json', {'directory': str(output), 'status': report['status'],
                  'capabilities': str(output/'capabilities.json'), 'errors': len(errors), 'receipts': len(rows)})
        print('[S0601 PROBE] ' + json.dumps({'directory': str(output), 'status': report['status'], 'failures': report['failures']}), flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if report['status'] != 'unsupported' else 2)


asyncio.ensure_future(run())
