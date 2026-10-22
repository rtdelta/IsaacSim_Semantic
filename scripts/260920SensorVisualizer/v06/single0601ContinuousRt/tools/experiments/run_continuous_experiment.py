"""Planned-target continuous capture. Bad poses are saved, never filtered."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import numpy as np
PROJECT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(PROJECT),str(PROJECT.parent)]
from tools.experiments.storage import EvidenceWriter,save,digest


def mounts(owner):
    from sensor_visualizer_v06.robot.sensor_pose import SensorPoses,mount_for_sensor
    reader=SensorPoses.__new__(SensorPoses);reader.stage=owner.stage;reader.units=1.;reader.entries={}
    for kind in ('cameras','lidars'):
        for entry in owner.registry[kind]:
            sid=('camera_'+entry['id']) if kind=='cameras' else entry['id']
            reader.entries[sid]={'mount_path':str(mount_for_sensor(owner.stage.GetPrimAtPath(entry['prim_path'])).GetPath())}
    return [dict(reader.read(sid),id=sid) for sid in reader.entries]


async def run():
    import omni.kit.app
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.engine_owner import EngineOwner
    from single0601_continuous_rt.native_probe_owner import NativeProbeOwner
    from single0601_continuous_rt.sensor_backend import pose_error
    from single0601_continuous_rt.diagnostics import process_resources
    spec=json.loads(Path(os.environ['S0601_EXPERIMENT_SPEC']).read_text())
    directory=PROJECT/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat']/'continuous'
    directory.mkdir(parents=True,exist_ok=False)
    job=load(PROJECT/'config/mixed_pair.json');job['diagnostics']={'native_trace':True}
    job['clock']['physics_hz']=spec.get('physics_hz',60);job['clock']['loop_hz']=spec.get('physics_hz',60)
    owner=(NativeProbeOwner if spec['scene']=='room' else EngineOwner)(PROJECT,job)
    if spec['scene']=='room':owner.heading=math.radians(spec.get('initial_yaw_deg',0.))
    writer=EvidenceWriter(directory,spec['queue_bytes'],spec['disk_bytes'])
    report={'schema_version':1,'status':'EXPERIMENT_FAILED','formal_continuous_acceptance':False,
        'spec':spec,'started_monotonic_ns':str(time.monotonic_ns())}
    active=False;first=last=None;target_steps=set();counts={};captured_states=0;mount_rows=[]
    deadline=time.monotonic()+spec['wall_timeout_s']
    def event(evidence,data):
        sid=evidence['sensor_id']
        if not active:return
        try:
            step,state=owner.ledger.exact_time(owner.epoch_id,int(evidence['source_time_ns']))
        except Exception as exc:
            writer.event('unassigned_events.jsonl',dict(evidence,mapping_error=str(exc)));return
        if step not in target_steps:return
        translation,rotation=pose_error(state['sensor_world_matrices_usd'][sid],evidence['rendered_to_world'])
        index=(step-first)//spec['stride'];seq=evidence['receipt_seq'];png=evidence['kind']=='camera'
        name='payloads/%s_%06d.%s'%(sid.replace('/','_'),seq,'png' if png else 'xyz')
        writer.payload(name,data,png=png)
        writer.event('native_events.jsonl',dict(evidence,experiment_id=spec['experiment_id'],repeat=spec['repeat'],
            source_epoch=owner.epoch_id,physical_step=step,target_index=index,block=spec['block'],phase='steady',
            historical_to_world=state['sensor_world_matrices_usd'][sid],actual_root=state['root'],
            translation_error_m=translation,rotation_error_rad=rotation,payload_path=name,
            payload_sha256=hashlib.sha256(data.tobytes()).hexdigest(),payload_hash_scope='decoded owned array bytes'))
        counts[(step,sid)]=counts.get((step,sid),0)+1
    def packet(evidence,data):
        if not active:return
        step,state=owner.ledger.exact_time(owner.epoch_id,int(evidence['source_time_ns']))
        if step not in target_steps:return
        index=(step-first)//spec['stride'];meta=evidence['native_event'];seq=evidence['receipt_seq']
        prefix=data[:512].copy();name='trace_samples/gmo_prefix_%06d.bin'%seq;writer.payload(name,prefix)
        meta.update(packet_prefix_path=name,packet_prefix_sha256=hashlib.sha256(prefix.tobytes()).hexdigest())
        if spec.get('full_gmo_all') or index in (0,spec['targets']//2,spec['targets']-1):
            meta['packet_path']=writer.payload('trace_samples/gmo_%06d.bin'%seq,data)
        else:meta['packet_path']=None
    def state_event(state):
        nonlocal captured_states
        if not active:return
        writer.event('actual_states.jsonl',state);captured_states+=1
        step=state['physical_step']
        if step in target_steps:
            snapshot={'schema_version':1,'snapshot_id':'%s:%d'%(owner.epoch_id,step),'session_id':owner.epoch_id,
                't_sim_s':(step-first)/spec.get('physics_hz',60),'state_revision':state['state_revision'],
                'mount_revision':state.get('mount_revision',0),'position_world_m':state['root']['position_m'],
                'quaternion_xyzw':state['root']['orientation_xyzw'],
                'joints_deg':{n:math.degrees(x) for n,x in zip(state.get('joints',{}).get('names',[]),state.get('joints',{}).get('position',[]))
                    if owner.motion and n in {j['name'] for j in owner.motion.config['joints']}},
                'mounts':mount_rows}
            writer.event('targets.jsonl',{'source_epoch':owner.epoch_id,'physical_step':step,'target_index':(step-first)//spec['stride'],
                'block':spec['block'],'actual_state':state,'snapshot':snapshot})
    try:
        await asyncio.wait_for(owner.initialize(),timeout=spec['init_timeout_s'])
        if spec['scene']=='scene18':
            mount_rows=mounts(owner)
            from pxr import UsdGeom
            domes=[p for p in owner.stage.Traverse() if p.GetTypeName()=='DomeLight']
            light_state={'policy':'preserve_authored','before':[{'path':str(p.GetPath()),'active':p.IsActive(),
                'visibility':str(UsdGeom.Imageable(p).ComputeVisibility()),'intensity':p.GetAttribute('inputs:intensity').Get()} for p in domes]}
            if spec.get('align_v06_lighting'):
                from sensor_visualizer_v06.lighting import select_dome
                from sensor_visualizer_v06.diagnostics import NullDiagnostics
                light_state=select_dome(owner.stage,owner.layer,'/environment_Fangshan_02/DomeLight','persistent_gated',NullDiagnostics())
            save(directory/'lighting_state.json',light_state)
        expected=[e['sensor_id'] for k in ('cameras','lidars') for e in owner.registry[k]]
        current=owner.manager.get_num_physics_steps();first=(current//spec['stride']+1)*spec['stride'];last=first+(spec['targets']-1)*spec['stride']
        target_steps=set(range(first,last+1,spec['stride']))
        report.update(source_epoch=owner.epoch_id,first_physical_step=first,last_physical_step=last,expected_sensors=expected,
            planned_target_count=spec['targets'],planned_event_count=spec['targets']*len(expected))
        owner.on_state=state_event;owner.on_receipt=event
        owner.on_reject=lambda error:writer.event('native_errors.jsonl',error)
        owner.backend.on_native_packet=packet
        # Keep complete same-event CameraParams metadata without changing production backend.
        original_receive=owner.backend._receive
        def observed_receive(native_writer,data):
            if native_writer.kind=='camera':
                value=next((v for k,v in data.items() if k=='CameraParams' or k.startswith('CameraParams-')),None)
                if value is not None and active:
                    writer.event('camera_params.jsonl',{'receipt_seq':owner.backend.sequence,'sensor_id':native_writer.entry['sensor_id'],
                        'params':{k:(v.tolist() if isinstance(v,np.ndarray) else str(v)) for k,v in value.items()}})
            original_receive(native_writer,data)
        owner.backend._receive=observed_receive
        save(directory/'environment.json',owner.environment());save(directory/'sensor_registry.json',owner.registry)
        save(directory/'render_profile.json',owner.render_profile);save(directory/'experiment_spec.json',spec)
        save(directory/'source_manifest.json',{'files':[{'path':str(path.relative_to(PROJECT.parent)),'sha256':digest(path)}
            for path in list((PROJECT/'single0601_continuous_rt').rglob('*.py'))+list((PROJECT.parent/'sensor_visualizer_v06').rglob('*.py'))+list((PROJECT/'tools/experiments').rglob('*.py'))]})
        initial=process_resources();rss_limit=max(4*1024**3,2*initial['peak_rss_bytes'])
        save(directory/'resource_budget.json',{'queue_bytes':spec['queue_bytes'],'disk_bytes':spec['disk_bytes'],'rss_limit_bytes':rss_limit,
            'wall_timeout_s':spec['wall_timeout_s'],'initial':initial,'backpressure':'stop and retain prefix; no physics pauses added'})
        profile={'speed_m_s':spec['speed_m_s'],'yaw_rate_deg_s':spec['yaw_rate_deg_s']}
        if spec['scene']=='room':owner.set_profile(profile)
        else:owner.controller.enqueue('acceptance','base_velocity',profile)
        active=True;owner.timeline.play();owner.timeline.commit();last_resource=time.monotonic()
        while owner.manager.get_num_physics_steps()<last+spec['stride']:
            await owner.app.next_update_async()
            if owner.error:raise RuntimeError(str(owner.error))
            if writer.error:raise RuntimeError(writer.error)
            if time.monotonic()>deadline:raise RuntimeError('experiment_wall_timeout')
            if time.monotonic()-last_resource>=1:
                resource=process_resources();writer.event('resources.jsonl',dict(resource,queue_bytes=writer.inflight,monotonic_ns=str(time.monotonic_ns())))
                if resource['rss_bytes']>rss_limit:raise RuntimeError('experiment_rss_budget')
                last_resource=time.monotonic()
        active=False;owner.timeline.pause();owner.timeline.commit()
        report.update(status='EXPERIMENT_COMPLETE',planned_target_coverage=sum(any((step,sid) in counts for sid in expected) for step in target_steps)/len(target_steps),
            all_sensor_coverage=sum(all((step,sid) in counts for sid in expected) for step in target_steps)/len(target_steps),
            saved_events=sum(counts.values()),duplicate_events=sum(n-1 for n in counts.values()),actual_states=captured_states)
    except Exception as exc:report.update(failure=str(exc),traceback=traceback.format_exc())
    finally:
        active=False
        try:await owner.close();report['cleanup']=owner.cleanup_report
        except Exception as exc:report['cleanup']={'passed':False,'error':str(exc)}
        report['finished_monotonic_ns']=str(time.monotonic_ns());save(directory/'run_result.json',report)
        try:await asyncio.to_thread(writer.close);report['raw_capture_integrity_ok']=True
        except Exception as exc:report.update(raw_capture_integrity_ok=False,save_failure=str(exc),status='EXPERIMENT_FAILED')
        save(directory.parent/'continuous_terminal.json',report)
        print('[PAIRED C] '+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if report['status']=='EXPERIMENT_COMPLETE' else 2)

asyncio.ensure_future(run())
