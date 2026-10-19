"""Bounded raw-first continuous room experiment with optional phase probes."""
import asyncio,hashlib,json,math,os,sys,time,traceback
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(PROJECT),str(PROJECT.parent)]
from tools.experiments.storage import EvidenceWriter,save,digest
from tools.clock_state.common import parent_for,target_table,safe_value
from tools.clock_state.raw_tap import capture,associate
from single0601_continuous_rt.native_probe_owner import NativeProbeOwner
from single0601_continuous_rt.sensor_backend import pose_error


class TableOwner(NativeProbeOwner):
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw);self.table={};self.offset=None;self.pre_step=None;self.calibration=[]
        self.probe=None;self.sink=None;self.app_update_id=0;self.stage_seq=0;self.trace_bytes=0;self.trace_limit=128*1024**2;self.table_write=True;self.write_phase='PRE'
        self.table_write_revision=0;self.last_table_write_step=None
        self.baseline=False
    def stamp(self):
        self.stage_seq+=1
        return {'stage_seq':self.stage_seq,'app_update_id':self.app_update_id,'monotonic_ns':str(time.monotonic_ns()),
            'physical_step':self.manager.get_num_physics_steps(),'simulation_time_ns':str(round(self.manager.get_simulation_time()*1e9)),
            'epoch_id':self.epoch_id,'scene_generation':self.scene_generation,
            'table_write_revision':self.table_write_revision,'last_table_write_step':self.last_table_write_step}
    def phase(self,name,extra=None):
        if self.baseline and name in ('physics_pre_before_write','physics_pre_after_write','physics_post_actual'):
            from pxr import Usd,UsdGeom
            row={'phase':name,'physical_step':self.manager.get_num_physics_steps(),
                'sim_time_s':self.manager.get_simulation_time(),'sim_time_ns':str(round(self.manager.get_simulation_time()*1e9)),
                'dt_s':float(extra['dt']),'matrix':np.array(UsdGeom.Xformable(self.stage.GetPrimAtPath('/RecoverySensor')).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).tolist(),
                'write_revision':self.table_write_revision,'app_update_id':self.app_update_id,'monotonic_ns':str(time.monotonic_ns())}
            self.trace_bytes+=len(json.dumps(row,allow_nan=False).encode('utf-8'))
            if self.trace_bytes>self.trace_limit:raise RuntimeError('Baseline trace budget')
            self.sink.event('baseline_physics.jsonl',row)
        if not self.probe:return
        self.phase_extra=dict(self.stamp(),phase=name,extra=extra)
        self.probe.capture(name)
    def event(self,name,kind,data):
        # StateTrace adapter: bounded async CPU writer; never flush Fabric/Hydra.
        data.update(self.phase_extra,timeline_time_s=self.timeline.get_current_time())
        try:
            p=self.probe.fabric_stage.GetPrimAtPath('/ExternalSimulationTime')
            attr=p.GetAttribute('omni:time') if p else None;v=attr.Get() if attr else None
            data['external_simulation_time_typed']={'value':safe_value(v),'python_type':type(v).__module__+'.'+type(v).__name__,
                'attribute_type':str(attr.GetTypeName()) if attr else None,'unit':'unverified; do not numerically compare without schema'}
        except Exception as exc:data['external_simulation_time_error']=str(exc)
        size=len(json.dumps(data,allow_nan=False).encode('utf-8'))
        self.trace_bytes+=size
        if self.trace_bytes>self.trace_limit:raise RuntimeError('Phase trace budget')
        self.sink.event('phase_clock_trace.jsonl',data)
    def _room_pre(self,dt,context=None):
        self.pre_step=self.manager.get_num_physics_steps()
        if not self.table:
            self.phase('physics_pre_before_write',{'dt':float(dt),'static_warmup':True})
            super()._room_pre(dt,context)
            self.phase('physics_pre_after_write',{'dt':float(dt),'static_warmup':True})
            return
        try:
            self.phase('physics_pre_before_write',{'dt':float(dt)})
            step=self.pre_step+self.offset;row=self.table.get(step)
            if row:
                from pxr import Gf
                skip=self.write_phase=='POST' or (row.get('hold') and row.get('hold_write_policy')=='SKIP_WRITE')
                if not skip:
                    if self.table_write:self.pose_op.Set(Gf.Matrix4d(row['matrix']))
                    else:super()._room_pre(dt,context)
                    self.table_write_revision+=1;self.last_table_write_step=step
                self.sink.event('pose_writes.jsonl',dict(self.stamp(),write_physical_step=step,table_motion_step=row['motion_step'],
                    position_m=row['position_m'],orientation_xyzw=row['orientation_xyzw'],matrix_parameter=row['matrix'],dt=float(dt),
                    write_mode='PRE_SKIPPED' if skip else ('PRE_TABLE_SET' if self.table_write else 'PRE_ORIGINAL_INCREMENTAL'),authored=not skip,hold=bool(row.get('hold'))))
            else:
                # Preserve old per-step authoring even during static warmup/drain.
                super()._room_pre(dt,context)
            self.phase('physics_pre_after_write',{'dt':float(dt),'table_step':step if row else None})
        except Exception as exc:self.error={'code':'clock_pre','message':str(exc)}
    def _room_post(self,dt,context=None):
        self.calibration.append({'pre_counter':self.pre_step,'post_counter':self.manager.get_num_physics_steps()}) if self.offset is None else None
        if self.table and self.write_phase=='POST':
            try:
                row=self.table.get(self.manager.get_num_physics_steps())
                if row:
                    from pxr import Gf
                    self.phase('physics_post_before_write',{'dt':float(dt)})
                    self.pose_op.Set(Gf.Matrix4d(row['matrix']))
                    self.table_write_revision+=1;self.last_table_write_step=row['physical_step']
                    self.sink.event('post_pose_writes.jsonl',dict(self.stamp(),write_physical_step=row['physical_step'],authored=True,write_mode='POST_TABLE_SET',matrix_parameter=row['matrix']))
                    self.phase('physics_post_after_write',{'dt':float(dt)})
            except Exception as exc:self.error={'code':'clock_post_write','message':str(exc)}
        super()._room_post(dt,context)
        try:self.phase('physics_post_actual',{'dt':float(dt)})
        except Exception as exc:self.error={'code':'clock_post','message':str(exc)}


def settings_snapshot(owner,spec):
    from isaacsim.core.rendering_manager import RenderingManager
    runner=RenderingManager._loop_runner
    result={'requested_physics_hz':spec['physics_hz'],'requested_loop_hz':spec['physics_hz'],
        'requested_tick_hz':10,'stage_time_codes_per_second':owner.stage.GetTimeCodesPerSecond(),
        'loop_manual_mode':runner.get_manual_mode(),'loop_manual_step_size':runner.get_manual_step_size(),
        'settings':{k:owner.settings.get(k) for k in ('/app/settings/fabricDefaultSimPeriodNumerator','/app/settings/fabricDefaultSimPeriodDenominator',
            '/app/runLoops/main/rateLimitEnabled','/app/runLoops/main/rateLimitFrequency','/app/player/useFixedTimeStepping',
            '/app/player/useFastMode','/app/asyncRendering','/rtx/hydra/supportMultiTickRate','/renderer/raytracingMotion/enabled',
            '/rtx/rendering/perSensorTickTlas','/rtx/scenedb/maxHistoryTransformCount')}}
    for method in ('get_target_framerate','get_time_codes_per_second','get_auto_update','get_play_every_frame'):
        try:result[method]=safe_value(getattr(owner.timeline,method)())
        except Exception as exc:result[method]={'unavailable':str(exc)}
    return result


async def run():
    import omni.kit.app
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.state_trace import StateTrace
    from single0601_continuous_rt.diagnostics import process_resources
    spec=json.loads(Path(os.environ['S0601_EXPERIMENT_SPEC']).read_text());parent=parent_for(PROJECT,spec);directory=parent/'continuous'
    directory.mkdir(parents=True,exist_ok=False)
    job=load(PROJECT/'config/mixed_pair.json');job['diagnostics']={'native_trace':True}
    job['clock'].update(physics_hz=spec['physics_hz'],loop_hz=spec['physics_hz'])
    owner=TableOwner(PROJECT,job);owner.heading=math.radians(spec.get('initial_yaw_deg',0));sink=EvidenceWriter(directory,spec['queue_bytes'],spec['disk_bytes'],compress_gmo=spec.get('compress_gmo',False))
    owner.sink=sink
    owner.baseline=spec.get('native_instant_baseline',False)
    result={'schema_version':1,'status':'EXPERIMENT_FAILED','formal_continuous_acceptance':False,'spec':spec,
        'started_monotonic_ns':str(time.monotonic_ns()),'expected_sensors':['lidar/MyAiry_front']}
    deadline=(int(os.environ['S0601_LAUNCH_MONOTONIC_NS'])/1e9+spec['wall_timeout_s']-30 if owner.baseline else time.monotonic()+spec['wall_timeout_s']);observing=False;seq=0;counts={};first=last=None;target_steps=set();anchors=[];state_count=0
    capture_epoch=capture_generation=None
    def state_event(state):
        nonlocal state_count
        if not observing:return
        sink.event('actual_states.jsonl',state);state_count+=1;step=state['physical_step']
        planned_hold=owner.table.get(step)
        if planned_hold and planned_hold.get('hold'):
            pe,re=pose_error(planned_hold['matrix'],state['sensor_world_matrices_usd']['lidar/MyAiry_front'])
            passed=pe<=1e-5 and re<=1e-6
            sink.event('hold_actual_states.jsonl',{'physical_step':step,'input_qualified':passed,'position_error_m':pe,
                'rotation_error_rad':re,'write_policy':planned_hold['hold_write_policy'],'scope':'whole world sensor pose; no parents/joints in room'})
            if not passed:owner.error={'code':'hold_actual_input_changed','message':'Held world sensor pose differs from predeclared actual pose'}
        if step in target_steps:
            planned=owner.table[step];m=state['sensor_world_matrices_usd']['lidar/MyAiry_front'];pe,re=pose_error(planned['matrix'],m)
            sink.event('targets.jsonl',{'source_epoch':owner.epoch_id,'physical_step':step,'target_index':(step-first)//spec['stride'],
                'block':spec['block'],'actual_state':state,'table_input_equivalence':{'passed':pe<=1e-5 and re<=1e-6,'translation_m':pe,'rotation_rad':re},
                'snapshot':{'schema_version':1,'snapshot_id':'%s:%d'%(owner.epoch_id,step),'session_id':owner.epoch_id,
                    't_sim_s':(step-first)/spec['physics_hz'],'state_revision':state['state_revision'],'mount_revision':0,
                    'position_world_m':state['root']['position_m'],'quaternion_xyzw':state['root']['orientation_xyzw'],'joints_deg':{},'mounts':[]}})
    def receive(native_writer,data):
        nonlocal seq
        if not observing:return
        number=seq;seq+=1
        try:
            owner.phase('writer_enter',{'diagnostic_sequence':number})
            raw=capture(data,native_writer,number,sink,{'source_epoch':capture_epoch,'scene_generation':capture_generation,
                'capability_id':owner.capability_id,'callback_physical_step':owner.manager.get_num_physics_steps(),
                'callback_simulation_time_ns':str(round(owner.manager.get_simulation_time()*1e9)),
                'app_update_id':owner.app_update_id,'phase':'warmup' if first is None else 'capture_or_drain'})
            event=associate(raw,owner.backend.iface.get_simulation_time_at_time,owner.ledger)
            if capture_epoch!=owner.epoch_id or capture_generation!=owner.scene_generation:
                event['rejection_reasons'].append('writer_creation_epoch_or_generation_differs_from_active_owner')
                event.update(formal_event_rejected=True,physical_step=None)
            step=event['physical_step']
            if step is not None:
                anchors.append({'physical_step':step,'source_time_ns':event['source_time_ns'],'diagnostic_event_id':event['diagnostic_event_id']})
            if step in target_steps:
                index=(step-first)//spec['stride'];state=event['actual_state'];m=state['sensor_world_matrices_usd']['lidar/MyAiry_front']
                event.update(target_index=index,historical_to_world=m,actual_root=state['root'],block=spec['block'])
                if event.get('rendered_to_world'):
                    pe,re=pose_error(m,event['rendered_to_world']);event.update(translation_error_m=pe,rotation_error_rad=re)
                counts[step]=counts.get(step,0)+1;sink.event('native_events.jsonl',event)
            else:sink.event('unassigned_events.jsonl',dict(event,unassigned_reason='no_exact_association' if step is None else 'outside_planned_targets'))
            if event['formal_event_rejected']:sink.event('event_rejections.jsonl',event)
            owner.phase('writer_exit',{'diagnostic_sequence':number})
        except Exception as exc:owner.error={'code':'raw_capture_failure','message':str(exc)}
    async def update(phase):
        owner.app_update_id+=1;before=owner.manager.get_num_physics_steps();started=time.monotonic_ns();owner.phase('app_update_enter')
        await owner.app.next_update_async();owner.phase('app_update_return')
        sink.event('app_updates.jsonl',{'app_update_id':owner.app_update_id,'phase':phase,'physical_step_before':before,
            'physical_step_after':owner.manager.get_num_physics_steps(),'started_monotonic_ns':str(started),'finished_monotonic_ns':str(time.monotonic_ns())})
        if owner.error:raise RuntimeError(str(owner.error))
        if sink.error:raise RuntimeError(sink.error)
        if time.monotonic()>deadline:raise RuntimeError('continuous_total_wall_timeout_including_init')
    try:
        await asyncio.wait_for(owner.initialize(),timeout=spec['init_timeout_s'])
        capture_epoch=owner.epoch_id;capture_generation=owner.scene_generation
        offsets={x['post_counter']-x['pre_counter'] for x in owner.calibration}
        if len(offsets)!=1 or not offsets.issubset({0,1}):raise RuntimeError('Unqualified PRE/POST counter semantics '+repr(offsets))
        owner.offset=offsets.pop();save(directory/'pre_post_counter_qualification.json',{'offset':owner.offset,'samples':owner.calibration})
        save(directory/'environment.json',owner.environment());save(directory/'sensor_registry.json',owner.registry)
        save(directory/'render_profile.json',owner.render_profile);save(directory/'experiment_spec.json',spec)
        save(directory/'effective_settings_before.json',settings_snapshot(owner,spec))
        if owner.baseline:
            from tools.native_instant_baseline.runtime import record
            record(directory,owner.stage,'/RecoverySensor',owner.backend.products[0].path,spec,
                {'initial_physics_updates':6,'static_updates':24,'product_created_at_step':owner.manager.get_num_physics_steps()})
            save(directory/'run_spec.json',spec)
        save(directory/('source_manifest_project.json' if owner.baseline else 'source_manifest.json'),{'files':[{'path':p.relative_to(PROJECT.parent).as_posix(),'sha256':digest(p)}
            for folder in (PROJECT/'single0601_continuous_rt',PROJECT.parent/'sensor_visualizer_v06',PROJECT/'tools/experiments',PROJECT/'tools/clock_state') for p in sorted(folder.rglob('*.py'))]})
        if spec['stage_probe']:owner.probe=StateTrace(owner,owner)
        owner.on_state=state_event;owner.backend._receive=receive;observing=True
        initial=process_resources();rss_limit=max(4*1024**3,2*initial['rss_bytes' if owner.baseline else 'peak_rss_bytes'])
        save(directory/'resource_budget.json',dict(queue_bytes=spec['queue_bytes'],disk_bytes=spec['disk_bytes'],trace_bytes=owner.trace_limit,
            rss_limit_bytes=rss_limit,initial=initial,backpressure='stop and retain; never pause to drain'))
        owner.timeline.play();owner.timeline.commit()
        # Fixed static observation window; no waiting until N accepted samples.
        for _ in range(spec['warmup_updates']):await update('static_warmup')
        if owner.baseline:
            from tools.native_instant_baseline.runtime import capture_settings
            capture_settings(directory,owner.stage)
        unique=sorted(set(a['physical_step'] for a in anchors));current=owner.manager.get_num_physics_steps()
        if spec.get('legacy_bridge'):
            # Exact old scheduling for the baseline bridge; native phase is verified offline, not assumed observed here.
            first=(current//spec['stride']+1)*spec['stride'];start=current+owner.offset
        else:
            if len(unique)<2 or any(b-a!=spec['stride'] for a,b in zip(unique,unique[1:])):raise RuntimeError('Unqualified native source tick anchor')
            anchor=unique[-1];first=anchor+((current-anchor)//spec['stride']+2)*spec['stride'];start=first-spec['stride']+1
        last=first+(spec['targets']-1)*spec['stride'];end=last+spec['stride']*spec.get('drain_cycles',1)
        owner.table=target_table(spec,start,end);target_steps=set(range(first,last+1,spec['stride']))
        owner.table_write=spec.get('table_write',True)
        owner.write_phase=spec.get('write_phase','PRE')
        if owner.write_phase not in ('PRE','POST'):raise ValueError('Unsupported write phase')
        if not owner.table_write:owner.set_profile({'speed_m_s':spec['speed_m_s'],'yaw_rate_deg_s':spec['yaw_rate_deg_s']})
        for row in owner.table.values():sink.event('target_pose_table.jsonl',row)
        save(directory/'planned_targets.json',{'first':first,'last':last,'steps':sorted(target_steps),'start_motion_step':start,
            'end':end,
            'native_anchor':anchors,'warmup_updates':spec['warmup_updates'],'target_phase_offset_steps':None if spec.get('legacy_bridge') else 0,
            'anchor_kind':'legacy_physics_counter_grid_verified_against_native_source_offline' if spec.get('legacy_bridge') else 'observed_native_source_tick'})
        result.update(source_epoch=owner.epoch_id,first_physical_step=first,last_physical_step=last,planned_target_count=spec['targets'],planned_event_count=spec['targets'])
        save(directory/'effective_settings_capture.json',settings_snapshot(owner,spec));last_resource=time.monotonic()
        while owner.manager.get_num_physics_steps()<end:
            await update('motion_and_drain')
            if time.monotonic()-last_resource>=1:
                r=process_resources();sink.event('resources.jsonl',dict(r,queue_bytes=sink.inflight,monotonic_ns=str(time.monotonic_ns())))
                if r['rss_bytes']>rss_limit:raise RuntimeError('RSS budget')
                last_resource=time.monotonic()
        observing=False;owner.timeline.pause();owner.timeline.commit()
        save(directory/'effective_settings_after.json',settings_snapshot(owner,spec))
        result.update(status='EXPERIMENT_COMPLETE',planned_target_coverage=len(counts)/spec['targets'],all_sensor_coverage=len(counts)/spec['targets'],
            saved_events=sum(counts.values()),duplicate_events=sum(n-1 for n in counts.values()),raw_events=seq,actual_states=state_count,trace_bytes=owner.trace_bytes)
    except Exception as exc:result.update(failure=str(exc),traceback=traceback.format_exc())
    finally:
        observing=False
        try:
            if owner.probe:owner.probe.close();owner.probe=None
            await owner.close();result['cleanup']=owner.cleanup_report
        except Exception as exc:
            result['cleanup']=dict(getattr(owner,'cleanup_report',{}) or {},passed=False,error=str(exc))
            result.update(status='EXPERIMENT_FAILED',failure_kind='lifecycle',failure='Owner cleanup failed after capture; retain all evidence')
        result['finished_monotonic_ns']=str(time.monotonic_ns());save(directory/'run_result.json',result)
        try:await asyncio.to_thread(sink.close)
        except Exception as exc:result.update(status='EXPERIMENT_FAILED',save_failure=str(exc))
        save(parent/'continuous_terminal.json',result);print('[CLOCK C] '+json.dumps(result),flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if result['status']=='EXPERIMENT_COMPLETE' else 2)


asyncio.ensure_future(run())
