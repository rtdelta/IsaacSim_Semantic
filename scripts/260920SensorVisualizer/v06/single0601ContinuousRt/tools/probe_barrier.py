"""Real single-event barrier fallback probe; all products persist across targets."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


async def run():
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.engine_owner import EngineOwner
    from single0601_continuous_rt.sensor_backend import BarrierBackend,pose_error
    from single0601_continuous_rt.barrier_driver import BarrierDriver
    from single0601_continuous_rt.common import save_json,source_ns
    import omni.replicator.core as rep
    output=PROJECT/'reports'/('barrier_probe_'+time.strftime('%Y%m%d_%H%M%S'))
    output.mkdir(parents=True)
    owner=EngineOwner(PROJECT,load(os.environ['S0601_JOB']))
    owner.moving=True
    rows,errors,seen=[],[],{}
    target=None
    report={'schema_version':1,'recording_id':owner.recording_id,'capability_id':owner.capability_id,
            'status':'unsupported','selected_backend':None,'tests':[],'failures':[]}
    def receive(e,array):
        if target is None:
            return
        try:
            step,state=owner.ledger.exact_time(owner.epoch_id,int(e['source_time_ns']))
            tr,ang=pose_error(state['sensor_world_matrices_usd'][e['sensor_id']],e['rendered_to_world'])
            rows.append(dict(e,physical_step=step,target_step=target,historical_to_world=state['sensor_world_matrices_usd'][e['sensor_id']],
                             translation_error_m=tr,rotation_error_rad=ang,raw_sha256=hashlib.sha256(array.tobytes()).hexdigest()))
            seen[e['sensor_id']]=e
        except Exception as exc:
            errors.append({'code':getattr(exc,'code','probe_state'),'message':str(exc),'evidence':e})
    owner.on_receipt=receive
    owner.on_reject=lambda e: errors.append(e) if target is not None else None
    try:
        await owner.initialize()
        owner.timeline.play()
        owner.timeline.commit()
        for _ in range(owner.job['render']['initial_warmup_min_updates']):
            await owner.app.next_update_async()
        owner.timeline.pause()
        owner.timeline.commit()
        owner.setting('/rtx/hydra/supportMultiTickRate',False)
        owner.setting('/rtx/rendering/perSensorTickTlas',False)
        owner.setting('/renderer/raytracingMotion/enabled',False)
        rep.orchestrator.set_capture_on_play(False)
        owner.backend.__class__=BarrierBackend
        owner.backend.use_manual_triggers()
        owner.backend.set_updates(False)
        expected={e['sensor_id'] for k in ('cameras','lidars') for e in owner.registry[k]}
        for index in range(24):
            target=((owner.manager.get_num_physics_steps()//6)+1)*6
            seen.clear()
            owner.backend.permit=lambda mapped_ns: True
            owner.backend.set_updates(False)
            owner.timeline.play()
            owner.timeline.commit()
            while owner.manager.get_num_physics_steps()<target:
                await owner.app.next_update_async()
                if owner.error:
                    raise RuntimeError(str(owner.error))
            if owner.manager.get_num_physics_steps()!=target:
                raise RuntimeError('Physical target boundary was skipped')
            owner.timeline.pause()
            owner.timeline.commit()
            owner.backend.set_updates(True)
            owner.backend.schedule()
            await asyncio.wait_for(owner.backend.render_once(),15)
            until=time.monotonic()+5
            while set(seen)!=expected and time.monotonic()<until:
                await owner.app.next_update_async()
            if set(seen)!=expected:
                raise RuntimeError('Barrier target did not return every selected route')
            owner.backend.set_updates(False)
        tests=[{'name':'barrier_exact_physical_time','passed':bool(rows) and all(r['physical_step']==r['target_step'] for r in rows),
                'reason':'Persistent products; native physical six-step target, paused Timeline, one manual write and rt_subframes=1',
                'sample_count':len(rows),'evidence_paths':['probe_receipts.json','probe_errors.json']},
               {'name':'barrier_rendered_pose','passed':bool(rows) and all(r['translation_error_m']<=.001 and r['rotation_error_rad']<=.0001 for r in rows),
                'reason':'Native transform versus immutable actual physical state','sample_count':len(rows),'evidence_paths':['probe_receipts.json']},
               {'name':'barrier_source_mapping','passed':not errors,'reason':'Same-event reference mapped to physical source time',
                'sample_count':len(rows),'evidence_paths':['probe_errors.json']},
               {'name':'barrier_distinct_motion','passed':all(len({json.dumps(r['historical_to_world']) for r in rows if r['sensor_id']==s})>=20 for s in expected),
                'reason':'Twenty distinct actual moving sensor states','sample_count':24,'evidence_paths':['probe_receipts.json']}]
        report['tests']=tests
        report['source_mapping']={s:{'annotator':'IsaacReadSimulationTime','clock_domain':'physics_simulation',
            'mapping_method':'get_simulation_time_at_time(ReferenceTime)','native_ref_kind':'rational_time',
            'native_ref_scope':next(r['native_ref']['scope'] for r in rows if r['sensor_id']==s),
            'max_native_lead_groups':0,'verified_max_inflight':1} for s in expected}
        report['state_capture_phase']='PHYSICS_PRE_STEP writes once; PHYSICS_POST_STEP actual snapshot; pause at exact target; manual single render'
        report['status']='barrier_verified' if all(t['passed'] for t in tests) else 'unsupported'
        report['selected_backend']='barrier' if report['status']=='barrier_verified' else None
        report['failures'] += [{'code':t['name'],'message':t['reason'],'evidence_paths':t['evidence_paths']} for t in tests if not t['passed']]
        save_json(output/'render_profile.json',{'effective':{k:owner.settings.get(k) for k in owner.saved_settings},'products':owner.render_profile['products']})
        save_json(output/'sensor_registry.json',owner.registry)
        save_json(output/'environment.json',owner.environment())
    except Exception as exc:
        errors.append({'code':getattr(exc,'code','barrier_probe'),'message':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()})
        report['failures'].append({'code':getattr(exc,'code','barrier_probe'),'message':str(exc),'evidence_paths':['probe_errors.json']})
    finally:
        target=None
        save_json(output/'probe_receipts.json',rows)
        save_json(output/'probe_errors.json',errors)
        try:
            await owner.close()
            report['cleanup_succeeded']=True
        except Exception as exc:
            report['cleanup_succeeded']=False
            report.update(status='unsupported',selected_backend=None)
            report['failures'].append({'code':'cleanup_failed','message':type(exc).__name__+': '+str(exc),'evidence_paths':[]})
        save_json(output/'capabilities.json',report)
        save_json(PROJECT/'reports/latest_probe.json',{'directory':str(output),'status':report['status'],
                'capabilities':str(output/'capabilities.json'),'errors':len(errors),'receipts':len(rows)})
        print('[S0601 BARRIER] '+json.dumps(report),flush=True)
        owner.app.post_uncancellable_quit(0 if report['status']=='barrier_verified' else 2)

asyncio.ensure_future(run())
