"""Known-room frozen reference using the original v06 driver lifecycle."""
import asyncio,hashlib,json,os,sys,time,traceback
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(PROJECT),str(PROJECT.parent)]
from tools.experiments.storage import EvidenceWriter,save
from tools.experiments.export_pair_trajectory import export
from tools.clock_state.common import parent_for


async def run():
    import omni.kit.app
    from pxr import Gf,Usd,UsdGeom
    from single0601_continuous_rt.config import load
    from single0601_continuous_rt.native_probe_owner import NativeProbeOwner
    from single0601_continuous_rt.sensor_backend import pose_error
    from single0601_continuous_rt.native_event import NativeEventAdapter
    from sensor_visualizer_v06.sensors import SensorDrivers
    from sensor_visualizer_v06.tickets import CaptureTicket
    spec=json.loads(Path(os.environ['S0601_EXPERIMENT_SPEC']).read_text())
    parent=parent_for(PROJECT,spec);trajectory=export(parent/'continuous')
    directory=parent/'frozen_room';directory.mkdir(exist_ok=False)
    job=load(PROJECT/'config/mixed_pair.json');job['diagnostics']={'native_trace':True}
    job['clock']['physics_hz']=spec.get('physics_hz',60);job['clock']['loop_hz']=spec.get('physics_hz',60)
    owner=NativeProbeOwner(PROJECT,job);writer=EvidenceWriter(directory,spec['queue_bytes'],spec['disk_bytes'],compress_gmo=spec.get('compress_gmo',False))
    original_setting=owner.setting
    def frozen_setting(key,value):
        if key in ('/rtx/hydra/supportMultiTickRate','/rtx/rendering/perSensorTickTlas','/renderer/raytracingMotion/enabled'):value=False
        original_setting(key,value)
    owner.setting=frozen_setting
    current=None;drivers=None;sequence=0;adapter=NativeEventAdapter()
    clock_suite=spec.get('suite')=='clock_state_v1'
    deadline=time.monotonic()+spec['frozen_timeout_s']
    report={'schema_version':1,'status':'EXPERIMENT_FAILED','reference_kind':'standalone known-room original v06 SensorDrivers frozen 16+2; NOT original v06 scene18',
        'requested_targets':spec['targets'],'written_groups':0,'formal_continuous_acceptance':False}
    def phase(name):save(directory/'phase_checkpoint.json',{'phase':name,'target_index':current['target_index'] if current else None})
    def matrix():return np.array(UsdGeom.Xformable(owner.stage.GetPrimAtPath('/RecoverySensor')).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    def qualify(target):
        translation,rotation=pose_error(target['actual_state']['sensor_world_matrices_usd']['lidar/MyAiry_front'],matrix())
        return {'passed':translation<=1e-5 and rotation<=1e-6,'sensor_translation_m':translation,'sensor_rotation_rad':rotation}
    try:
        phase('initialize_owner')
        await asyncio.wait_for(owner.initialize(sensor_products=False),timeout=spec['init_timeout_s'])
        drivers=await SensorDrivers.create(owner.stage,owner.layer,owner.registry,None,owner.scene_generation,owner.app,None,backend='persistent_gated')
        drivers.resource_policy='keepalive';drivers.set_capture_active(True)
        original_receive=drivers._receive
        for native_writer,product in zip(drivers.writers,drivers.products):
            native_writer.detach()
            annot=drivers.rep.AnnotatorRegistry.get_annotator('GenericModelOutput',device='cpu',do_array_copy=True)
            native_writer.annotators=list(native_writer.annotators)+[annot]
            native_writer.attach([product.path],trigger=None)
        def observed_receive(native_writer,data):
            nonlocal sequence
            ticket=native_writer.pending;original_receive(native_writer,data)
            if current is None or ticket is None:return
            readers=drivers.snapshots.get(('lidars','MyAiry_front'))
            if readers is None:return
            owned=np.array(readers['IsaacExtractRTXSensorPointCloud']['data'].reshape(-1,3),dtype='<f4',order='C',copy=True)
            rendered=np.array(readers['IsaacExtractRTXSensorPointCloud']['info']['transform']).reshape(4,4)
            historical=matrix();translation,rotation=pose_error(historical,rendered);seq=sequence;sequence+=1
            name=writer.payload('payloads/lidar_%06d.xyz'%seq,owned)
            row={'sensor_id':'lidar/MyAiry_front','kind':'lidar','receipt_seq':seq,'source_epoch':current['source_epoch'],
                'physical_step':current['physical_step'],'target_index':current['target_index'],'attempt_id':ticket.attempt_id,
                'source_time_ns':str(round(readers['IsaacReadSimulationTime']['simulationTime']*1e9)),
                'expected_time_ns':str(ticket.expected_sim_ns),'historical_to_world':historical.tolist(),'rendered_to_world':rendered.tolist(),
                'translation_error_m':translation,'rotation_error_rad':rotation,'shape':list(owned.shape),'dtype':str(owned.dtype),
                'raw_nbytes':owned.nbytes,'ownership':'owned_cpu','payload_path':name,'payload_sha256':hashlib.sha256(owned.tobytes()).hexdigest()}
            raw=next((v for k,v in data.items() if k=='GenericModelOutput' or k.startswith('GenericModelOutput-')),None)
            if raw is not None:
                meta,packet=adapter.capture(raw);prefix=packet[:512].copy()
                meta['packet_prefix_path']=writer.payload('trace_samples/gmo_prefix_%06d.bin'%seq,prefix)
                meta['packet_prefix_sha256']=hashlib.sha256(prefix.tobytes()).hexdigest()
                meta['packet_path']=writer.payload('trace_samples/gmo_%06d.bin'%seq,packet) if spec.get('full_gmo_all') or current['target_index'] in (0,spec['targets']//2,spec['targets']-1) else None
                row['native_event']=meta
            writer.event('native_events.jsonl',row)
        drivers._receive=observed_receive
        await drivers.render(4)
        save(directory/'environment.json',owner.environment());save(directory/'render_profile.json',owner.render_profile)
        save(directory/'sensor_registry.json',owner.registry);save(directory/'experiment_spec.json',spec)
        if not clock_suite:deadline=time.monotonic()+spec['frozen_timeout_s']
        if clock_suite:
            from single0601_continuous_rt.diagnostics import process_resources
            initial=process_resources();rss_limit=max(4*1024**3,2*initial['peak_rss_bytes'])
            save(directory/'resource_budget.json',{'rss_limit_bytes':rss_limit,'initial':initial,'wall_timeout_includes_initialize':True})
        for entry in trajectory['entries']:
            current=entry['target']
            if current is None:raise RuntimeError('Missing actual C target state')
            phase('advance')
            if current['target_index']:
                drivers.suspend_all('advance');owner.timeline.set_auto_update(True);owner.timeline.play();owner.timeline.commit()
                for _ in range(spec['stride']):await owner.app.next_update_async()
                owner.timeline.pause();owner.timeline.commit()
            owner.pose_op.Set(Gf.Matrix4d(current['actual_state']['sensor_world_matrices_usd']['lidar/MyAiry_front']))
            before=qualify(current);stamp=round(owner.manager.get_simulation_time()*1e9)
            writer.event('applied_states.jsonl',{'target_index':current['target_index'],'source_epoch':current['source_epoch'],
                'physical_step':current['physical_step'],'frozen_native_time_ns':str(stamp),'sensor_matrix':matrix().tolist(),'input_equivalence':before})
            if not before['passed']:raise RuntimeError('Frozen room input qualification failed')
            def frozen():
                if not qualify(current)['passed'] or round(owner.manager.get_simulation_time()*1e9)!=stamp:raise RuntimeError('Frozen actual input changed')
            phase('warm16');await drivers.warm_cameras(16);frozen()
            ticket=CaptureTicket(owner.recording_id,spec['experiment_id'],current['target_index'],owner.scene_generation,stamp,
                owner.state_revision,frozenset({'lidars/MyAiry_front'}),30.)
            phase('capture2');await drivers.acquire(ticket,2,owner.app,frozen,8)
            after=qualify(current)
            writer.event('capture_results.jsonl',{'target_index':current['target_index'],'input_equivalence_after':after,'accepted_attempt_id':0,
                'received_events':len(ticket.received),'native_clock_frozen':round(owner.manager.get_simulation_time()*1e9)==stamp,'original_ticket_complete':ticket.complete})
            if not ticket.complete:raise RuntimeError('Original driver ticket incomplete')
            report['written_groups']+=1
            if clock_suite:
                resource=process_resources();writer.event('resources.jsonl',resource)
                if resource['rss_bytes']>rss_limit:raise RuntimeError('Frozen room RSS budget exceeded')
            if time.monotonic()>deadline:raise RuntimeError('Frozen room wall budget exceeded')
        report.update(status='EXPERIMENT_COMPLETE',pair_input_equivalence_ok=True)
    except Exception as exc:report.update(failure=str(exc),traceback=traceback.format_exc())
    finally:
        current=None;phase('cleanup')
        try:
            if drivers:
                await drivers.finish_generation();drivers.detach();await owner.app.next_update_async()
                drivers.destroy();await owner.app.next_update_async()
            await owner.close();report['cleanup']=owner.cleanup_report
        except Exception as exc:
            report['cleanup']=dict(getattr(owner,'cleanup_report',{}) or {},passed=False,error=str(exc))
            if clock_suite:report.update(status='EXPERIMENT_FAILED',failure_kind='lifecycle',failure='Owner cleanup failed after capture; retain all evidence')
        save(directory/'run_result.json',report)
        try:await asyncio.to_thread(writer.close)
        except Exception as exc:report.update(status='EXPERIMENT_FAILED',save_failure=str(exc))
        save(parent/'frozen_terminal.json',report);print('[ROOM F] '+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if report['status']=='EXPERIMENT_COMPLETE' else 2)

asyncio.ensure_future(run())
