"""Bounded real-SDK capability gate before any formal ticket is issued."""
import hashlib
import json
import time
from .common import ContractError, save_json, file_hash
from .sensor_backend import pose_error


async def probe(owner, directory, samples=24):
    directory.mkdir(parents=True, exist_ok=True)
    expected = {e['sensor_id'] for k in ('cameras','lidars') for e in owner.registry[k]}
    rows, failures, owned = [], [], {}
    ticks = {s:set() for s in expected}
    phase = 'moving'
    previous_callbacks = owner.on_receipt, owner.on_reject
    previous_moving = owner.moving
    owner.moving = True
    def receive(evidence, array):
        if phase != 'moving':
            return
        sid = evidence['sensor_id']
        if len(ticks[sid]) >= samples:
            return
        try:
            step, state = owner.ledger.exact_time(owner.epoch_id,int(evidence['source_time_ns']))
            tr, angle = pose_error(state['sensor_world_matrices_usd'][sid],evidence['rendered_to_world'])
            rows.append(dict(evidence,physical_step=step,historical_to_world=state['sensor_world_matrices_usd'][sid],
                             translation_error_m=tr,rotation_error_rad=angle,state_revision=state['state_revision']))
            ticks[sid].add(int(evidence['source_time_ns']))
            if sid not in owned:
                owned[sid] = array,hashlib.sha256(array.tobytes()).hexdigest()
        except Exception as exc:
            failures.append({'code':getattr(exc,'code','probe_state'),'sensor_id':sid,'message':str(exc)})
    def reject(error):
        if phase == 'moving':
            failures.append(error)
    owner.on_receipt, owner.on_reject = receive, reject
    owner.timeline.play()
    owner.timeline.commit()
    deadline = time.monotonic()+120
    updates = 0
    try:
        while not all(len(t)>=samples for t in ticks.values()):
            if time.monotonic()>deadline:
                raise ContractError('probe_deadline','Insufficient real moving sensor events in 120 wall seconds')
            await owner.app.next_update_async()
            updates += 1
            if owner.error:
                raise ContractError(owner.error['code'],owner.error['message'])
        phase = 'paused'
        before = owner.manager.get_simulation_time()
        owner.setting('/app/player/playSimulations',False)
        for _ in range(10):
            await owner.app.next_update_async()
        frozen = owner.manager.get_simulation_time()
        phase = 'resuming'
        owner.setting('/app/player/playSimulations',True)
        for _ in range(12):
            await owner.app.next_update_async()
        common = set.intersection(*ticks.values())
        ordered = sorted(common)
        distinct = {s:len({json.dumps(r['historical_to_world']) for r in rows if r['sensor_id']==s}) for s in expected}
        tests = []
        def test(name,passed,reason,n):
            tests.append({'name':name,'passed':bool(passed),'reason':reason,'sample_count':n,
                          'evidence_paths':['capability_probe/receipts.json','capability_probe/errors.json']})
        test('native_capture_on_play',all(len(t)>=samples for t in ticks.values()),'Persistent Writer callbacks; Timeline playing',len(rows))
        test('same_event_source_mapping',not failures,'Native ReferenceTime mapping cross-checked with same-event IsaacReadSimulationTime',len(rows))
        test('rendered_pose_actual_history',all(r['translation_error_m']<=.001 and r['rotation_error_rad']<=.0001 for r in rows),'Real motion, native rendered matrix against actual pre-render physical state',len(rows))
        test('owned_cpu_lifetime',all(hashlib.sha256(a.tobytes()).hexdigest()==h for a,h in owned.values()),'Retained independent CPU arrays unchanged over later native renders',len(owned))
        test('common_native_10hz_phase',len(common)>=20 and all(abs(b-a-100000000)<=2 for a,b in zip(ordered,ordered[1:])),'Common physical source grid; no nearest-neighbour alignment',len(common))
        test('distinct_moving_samples',all(n>=20 for n in distinct.values()),'At least twenty distinct actual poses for every selected sensor',min(distinct.values()))
        test('physical_pause_resume',before==frozen and owner.manager.get_simulation_time()>frozen,'Ten app updates with frozen physical time, then resumed physical steps',22)
        report = {'schema_version':1,'recording_id':owner.recording_id,'capability_id':owner.capability_id,
                  'status':'continuous_verified' if all(t['passed'] for t in tests) else 'unsupported',
                  'selected_backend':'continuous' if all(t['passed'] for t in tests) else None,'tests':tests,
                  'source_mapping':{s:{'annotator':'IsaacReadSimulationTime','clock_domain':'physics_simulation',
                      'mapping_method':'get_simulation_time_at_time(ReferenceTime)','native_ref_kind':'rational_time',
                      'native_ref_scope':next(r['native_ref']['scope'] for r in rows if r['sensor_id']==s),
                      'max_native_lead_groups':None,'verified_max_inflight':1} for s in sorted(expected)},
                  'state_capture_phase':'prescribed motion PHYSICS_PRE_STEP -100; actual readback PHYSICS_POST_STEP 100; render callback later',
                  'failures':failures+[{'code':t['name'],'message':t['reason'],'evidence_paths':t['evidence_paths']} for t in tests if not t['passed']],
                  'max_native_lead_groups':None,'actual_max_inflight_groups':1,'initial_warmup_updates':updates,
                  'restriction':'Unknown native lead: exactly one reserved target; safe-boundary physical backpressure'}
        save_json(directory/'receipts.json',rows)
        save_json(directory/'errors.json',failures)
        return report
    finally:
        owner.on_receipt, owner.on_reject = previous_callbacks
        owner.moving = previous_moving
        owner.motion.base_controller.hold()
        owned.clear()
