"""C1/C2 real native trace in one owned Kit; diagnostics never publish READY."""
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
    import omni.kit.app
    from single0601_continuous_rt.common import save_json,file_hash,utc
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.engine_owner import EngineOwner
    from single0601_continuous_rt.state_trace import BoundedTrace,StateTrace
    from single0601_continuous_rt.sensor_backend import pose_error
    from single0601_continuous_rt.diagnostics import process_resources
    mode=os.environ.get('S0601_NATIVE_PROFILE','mixed')
    profiles={'static':{'speed_m_s':0.,'yaw_rate_deg_s':0.},
              'translation':{'speed_m_s':1.,'yaw_rate_deg_s':0.},
              'rotation':{'speed_m_s':0.,'yaw_rate_deg_s':10.},
              'mixed':{'speed_m_s':.3,'yaw_rate_deg_s':3.}}
    if mode not in profiles:raise ValueError('Unknown diagnostic motion profile')
    directory=PROJECT/'reports/continuous_recovery'/('native_'+time.strftime('%Y%m%d_%H%M%S')+'_'+mode)
    directory.mkdir(parents=True,exist_ok=False)
    save_json(PROJECT/'reports/latest_native_probe.json',{'directory':str(directory),'status':'initializing'})
    job=load(os.environ['S0601_JOB'])
    job['diagnostics']=dict(job.get('diagnostics',{}),native_trace=True)
    job['render']['sensor_pose_mode']=os.environ.get('S0601_NATIVE_RIG','mounted')
    motion_history=os.environ.get('S0601_NATIVE_MOTION_HISTORY','default')
    if motion_history not in ('default','off'):raise ValueError('Unknown motion history diagnostic mode')
    if motion_history=='off':job['render']['motion_bvh']=False
    tlas=os.environ.get('S0601_NATIVE_TLAS','sensor')
    if tlas not in ('sensor','frame'):raise ValueError('Unknown native diagnostic TLAS mode')
    if tlas=='frame':job['diagnostics']['per_sensor_tlas']=False
    scene_mode=os.environ.get('S0601_NATIVE_SCENE','scene18')
    if scene_mode=='room':
        from single0601_continuous_rt.native_probe_owner import NativeProbeOwner
        owner=NativeProbeOwner(PROJECT,job)
    elif scene_mode=='scene18':owner=EngineOwner(PROJECT,job)
    else:raise ValueError('Unknown native diagnostic scene')
    rows,errors,counts=[],[],{}
    phase='initializing'
    log=BoundedTrace(directory)
    trace=None
    saved_pause=None
    deadline=time.monotonic()+120
    report={'schema_version':1,'scope':'native event diagnostic; no formal commits or READY',
            'started_utc':utc(),'profile':mode,'motion':profiles[mode],'requested_events_per_sensor':40,
            'status':'failed','runtime_fallback':False,'scene_mode':scene_mode,
            'sensor_pose_mode':job['render']['sensor_pose_mode'],'motion_history':motion_history,'tlas':tlas}
    def rejected(error):
        item=dict(error,phase=phase)
        errors.append(item)
        log.event('native_errors.jsonl','rejected',item)
    def packet(evidence,data):
        sid=evidence['sensor_id']
        if phase!='moving' or counts.get(sid,0)>=40:return
        meta=evidence['native_event']
        prefix=data[:512].copy()
        meta['packet_prefix_path']=log.payload('gmo_prefix_%06d.bin'%evidence['receipt_seq'],prefix)
        meta['packet_prefix_sha256']=hashlib.sha256(prefix.tobytes()).hexdigest()
        meta['packet_prefix_bytes']=prefix.nbytes
        if counts.get(sid,0) in (0,20,39):
            meta['packet_path']=log.payload('gmo_%06d.bin'%evidence['receipt_seq'],data)
        else:
            meta['packet_path']=None
            meta['packet_omitted_reason']='Fixed first/middle/last full-packet sampling under 128MiB trace budget; all native metadata and packet prefixes retained'
    def received(evidence,data):
        sid=evidence['sensor_id']
        if phase!='moving' or counts.get(sid,0)>=40:return
        try:
            step,state=owner.ledger.exact_time(owner.epoch_id,int(evidence['source_time_ns']))
            tr,rot=pose_error(state['sensor_world_matrices_usd'][sid],evidence['rendered_to_world'])
            path=log.payload('payload_%06d.bin'%evidence['receipt_seq'],data) if evidence['kind']=='lidar' or counts.get(sid,0) in (0,20,39) else None
            row=dict(evidence,physical_step=step,historical_to_world=state['sensor_world_matrices_usd'][sid],
                     actual_root=state['root'],translation_error_m=tr,rotation_error_rad=rot,
                     payload_path=path,payload_sha256=hashlib.sha256(data.tobytes()).hexdigest())
            rows.append(row);counts[sid]=counts.get(sid,0)+1
            log.event('native_events.jsonl','receipt',row)
        except Exception as exc:
            rejected({'code':getattr(exc,'code','native_trace'),'message':str(exc),'sensor_id':sid})
    try:
        await asyncio.wait_for(owner.initialize(),timeout=max(.001,deadline-time.monotonic()))
        expected=sorted(e['sensor_id'] for k in ('cameras','lidars') for e in owner.registry[k])
        counts.update({sid:0 for sid in expected})
        owner.on_receipt=received;owner.on_reject=rejected
        owner.backend.on_native_packet=packet
        trace=StateTrace(owner,log)
        owner.on_state=lambda state:trace.capture('physics_post',state)
        settings=['/app/hydraEngine/waitIdle','/app/updateOrder/checkForHydraRenderComplete',
                  '/app/asyncRendering','/rtx/hydra/supportMultiTickRate','/rtx/rendering/perSensorTickTlas',
                  '/renderer/raytracingMotion/enabled','/app/settings/fabricDefaultSimPeriodNumerator',
                  '/app/settings/fabricDefaultSimPeriodDenominator']
        report['effective_settings']={key:owner.settings.get(key) for key in settings}
        report['actual_link_pose_interfaces']=[n for n in dir(owner.motion.articulation) if ('link' in n or 'body' in n) and ('pose' in n or 'transform' in n)] if owner.motion else []
        save_json(directory/'environment.json',owner.environment())
        save_json(directory/'job_spec.json',job)
        save_json(directory/'sensor_registry.json',owner.registry)
        save_json(directory/'render_profile.json',owner.render_profile)
        save_json(directory/'source_manifest.json',{'schema_version':1,'files':[{'path':p.relative_to(PROJECT).as_posix(),'sha256':file_hash(p)} for p in PROJECT.rglob('*.py') if not any(x in p.parts for x in ('reports','__pycache__','.deploy_backups'))]})
        resources=process_resources()
        report['resource_budget']={'trace_bytes':log.max_bytes,'recording_credit_bytes':job['pipeline']['max_buffer_bytes'],
            'kit_rss_limit_bytes':max(4*1024**3,2*resources['peak_rss_bytes']),
            'scope':'Diagnostic Kit RSS bound frozen after initialization; distinct from recording buffer credit',
            'initial_resources':resources}
        save_json(directory/'resource_budget.json',report['resource_budget'])
        if scene_mode=='room':owner.set_profile(profiles[mode])
        else:owner.controller.enqueue('acceptance','base_velocity',profiles[mode])
        phase='moving'
        save_json(PROJECT/'reports/latest_native_probe.json',{'directory':str(directory),'status':'sampling','counts':counts})
        owner.timeline.play();owner.timeline.commit()
        while not all(n>=40 for n in counts.values()):
            if time.monotonic()>deadline:raise RuntimeError('Native trace wall deadline exceeded')
            await owner.app.next_update_async()
            trace.capture('app_after_update')
            if owner.error:raise RuntimeError(str(owner.error))
            if len(errors)>=8 and not any('native_event' in r for r in rows):
                raise RuntimeError('GMO event acquisition repeatedly rejected; inspect native_errors')
            if process_resources()['rss_bytes']>report['resource_budget']['kit_rss_limit_bytes']:
                raise RuntimeError('Kit diagnostic RSS bound exceeded')
        phase='paused_diagnostic'
        save_json(PROJECT/'reports/latest_native_probe.json',{'directory':str(directory),'status':phase,'counts':counts})
        owner.setting('/app/player/playSimulations',False)
        saved_pause=owner.manager.get_simulation_time()
        for _ in range(10):
            await owner.app.next_update_async();trace.capture('paused_update')
        report['physics_pause_frozen']=owner.manager.get_simulation_time()==saved_pause
        owner.setting('/app/player/playSimulations',True)
        phase='resuming_diagnostic'
        save_json(PROJECT/'reports/latest_native_probe.json',{'directory':str(directory),'status':phase,'counts':counts})
        for _ in range(12):
            await owner.app.next_update_async();trace.capture('resuming_update')
        report.update(status='diagnostic_completed',counts=counts,rows=len(rows),
                      errors_by_phase={p:sum(e['phase']==p for e in errors) for p in {e['phase'] for e in errors}},
                      pose_bad_rows=sum(r['translation_error_m']>.001 or r['rotation_error_rad']>.0001 for r in rows))
    except Exception as exc:
        report['failure']={'code':getattr(exc,'code','native_probe'),'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        phase='cleanup'
        if trace:trace.close()
        try:
            await owner.close();report['cleanup']=owner.cleanup_report
        except Exception as exc:
            report['cleanup']={'passed':False,'message':str(exc)}
        log.close()
        report.update(finished_utc=utc(),trace_bytes=log.bytes,counts=counts)
        save_json(directory/'mechanism_report.json',report)
        save_json(PROJECT/'reports/latest_native_probe.json',{'directory':str(directory),'status':report['status'],'counts':counts})
        print('[NATIVE PROBE] '+json.dumps({k:v for k,v in report.items() if k not in ('failure','effective_settings','actual_link_pose_interfaces','resource_budget')}),flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if report['status']=='diagnostic_completed' and report['cleanup'].get('passed') else 2)

asyncio.ensure_future(run())
