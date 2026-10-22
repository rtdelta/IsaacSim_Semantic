"""Read-only original v06 module reuse with exact actual-state pairing."""
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
PROJECT=Path(__file__).resolve().parents[2];V06=PROJECT.parent
sys.path[:0]=[str(PROJECT),str(V06)]
from tools.experiments.storage import EvidenceWriter,save,digest
from tools.experiments.export_pair_trajectory import export


def equivalence(reference,actual):
    from single0601_continuous_rt.geometry import matrix_from_pose
    from single0601_continuous_rt.sensor_backend import pose_error
    a=reference['actual_state'];root=a['root']
    translation,rotation=pose_error(matrix_from_pose(root['position_m'],root['orientation_xyzw']),
        matrix_from_pose(actual['root_position'],actual['root_xyzw']))
    joint_errors=[abs(x-y) for x,y in zip(a['joints']['position'],actual['positions'])]
    if a['joints']['names']!=actual['names']:raise ValueError('Actual joint identities differ')
    matrices={sid:dict(zip(('translation_m','rotation_rad'),pose_error(matrix,m)))
        for sid,m in actual['sensor_world_matrices_usd'].items() for matrix in [a['sensor_world_matrices_usd'][sid]]}
    passed=translation<=1e-5 and rotation<=1e-6 and max(joint_errors,default=0)<=1e-6 and all(
        m['translation_m']<=1e-5 and m['rotation_rad']<=1e-6 for m in matrices.values())
    return {'passed':passed,'root_translation_m':translation,'root_rotation_rad':rotation,
        'max_joint_error_rad':max(joint_errors,default=0),'sensor_errors':matrices,
        'thresholds':{'position_m':1e-5,'rotation_rad':1e-6,'joint_rad':1e-6}}


async def run():
    import omni.kit.app
    from pxr import Usd,UsdGeom
    from sensor_visualizer_v06.contracts import load_job
    from sensor_visualizer_v06.scene import SceneStepper
    from sensor_visualizer_v06.pipeline import RecordPipeline
    from sensor_visualizer_v06.diagnostics import RunDiagnostics
    from single0601_continuous_rt.sensor_backend import pose_error
    from single0601_continuous_rt.native_event import NativeEventAdapter
    spec=json.loads(Path(os.environ['S0601_EXPERIMENT_SPEC']).read_text())
    parent=PROJECT/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat']
    trajectory=export(parent/'continuous');directory=parent/'frozen_v06';directory.mkdir(exist_ok=False)
    source=json.loads((parent/'continuous/experiment_spec.json').read_text())
    job=load_job(overrides={'scene':json.loads((PROJECT/'config/mixed_pair.json').read_text())['scene'],
        'output_directory':str(directory),'groups':spec['targets'],'sensors':{'camera_ids':['front'],'lidar_ids':['MyAiry_front']},
        'capture':{'backend':'persistent_gated','resource_policy':'keepalive'},'pipeline':{'encoder_workers':2}})
    job['replay']={'mode':'explicit_pair','trajectory':str(parent/'pair_trajectory.json')}
    diagnostics=RunDiagnostics(directory,job['diagnostics'],V06,directory=directory/'diagnostics')
    scene=SceneStepper(V06,job,diagnostics);pipeline=None
    writer=EvidenceWriter(directory,spec['queue_bytes'],spec['disk_bytes'])
    report={'schema_version':1,'status':'EXPERIMENT_FAILED','reference_kind':'original v06 scene18 persistent_gated keepalive 16+2',
        'formal_continuous_acceptance':False,'requested_targets':spec['targets'],'written_groups':0}
    current=None;sequence=0;adapter=NativeEventAdapter();deadline=time.monotonic()+spec['frozen_timeout_s']
    def actual_state():
        actual=scene.motion.snapshot(scene.native_time())
        return dict(actual,sensor_world_matrices_usd={('camera/' if kind=='cameras' else 'lidar/')+e['id']:
            np.array(UsdGeom.Xformable(scene.stage.GetPrimAtPath(e['prim_path'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).tolist()
            for kind in ('cameras','lidars') for e in scene.registry[kind]})
    try:
        await asyncio.wait_for(scene.initialize(),timeout=spec['init_timeout_s'])
        scene.capture_id='paired_'+spec['experiment_id']+'_'+spec['repeat'];scene.drivers.resource_policy='keepalive'
        original_receive=scene.drivers._receive
        # Extra read-only GMO evidence stays in this adapter; original v06 files are untouched.
        for native_writer,product in zip(scene.drivers.writers,scene.drivers.products):
            if native_writer.kind=='lidars':
                native_writer.detach()
                annot=scene.drivers.rep.AnnotatorRegistry.get_annotator('GenericModelOutput',device='cpu',do_array_copy=True)
                native_writer.annotators=list(native_writer.annotators)+[annot]
                native_writer.attach([product.path],trigger=None)
        def observed_receive(native_writer,data):
            nonlocal sequence
            ticket=native_writer.pending
            original_receive(native_writer,data)
            if current is None or ticket is None:return
            readers=scene.drivers.snapshots.get((native_writer.kind,native_writer.entry['id']))
            if readers is None:return
            sid=('camera/' if native_writer.kind=='cameras' else 'lidar/')+native_writer.entry['id'];kind='camera' if native_writer.kind=='cameras' else 'lidar'
            if kind=='camera':
                owned=np.array(readers['rgb'][:,:,:3],dtype=np.uint8,order='C',copy=True)
                rendered=np.linalg.inv(np.array(readers['CameraParams']['cameraViewTransform']).reshape(4,4))
            else:
                owned=np.array(readers['IsaacExtractRTXSensorPointCloud']['data'].reshape(-1,3),dtype='<f4',order='C',copy=True)
                rendered=np.array(readers['IsaacExtractRTXSensorPointCloud']['info']['transform']).reshape(4,4)
            historical=actual_state()['sensor_world_matrices_usd'][sid];translation,rotation=pose_error(historical,rendered)
            seq=sequence;sequence+=1;name='payloads/%s_%06d.%s'%(sid.replace('/','_'),seq,'png' if kind=='camera' else 'xyz')
            writer.payload(name,owned,png=kind=='camera')
            row={'sensor_id':sid,'kind':kind,'receipt_seq':seq,'source_time_ns':str(round(readers['IsaacReadSimulationTime']['simulationTime']*1e9)),
                'expected_time_ns':str(ticket.expected_sim_ns),'source_epoch':current['source_epoch'],
                'physical_step':current['physical_step'],'target_index':current['target_index'],'attempt_id':ticket.attempt_id,
                'historical_to_world':historical,'rendered_to_world':rendered.tolist(),'translation_error_m':translation,'rotation_error_rad':rotation,
                'shape':list(owned.shape),'dtype':str(owned.dtype),'raw_nbytes':owned.nbytes,'ownership':'owned_cpu',
                'payload_path':name,'payload_sha256':hashlib.sha256(owned.tobytes()).hexdigest(),'payload_hash_scope':'decoded owned array bytes'}
            if kind=='lidar':
                raw=next((v for k,v in data.items() if k=='GenericModelOutput' or k.startswith('GenericModelOutput-')),None)
                if raw is not None:
                    meta,packet=adapter.capture(raw);prefix=packet[:512].copy()
                    meta['packet_prefix_path']=writer.payload('trace_samples/gmo_prefix_%06d.bin'%seq,prefix)
                    meta['packet_prefix_sha256']=hashlib.sha256(prefix.tobytes()).hexdigest()
                    meta['packet_path']=writer.payload('trace_samples/gmo_%06d.bin'%seq,packet) if current['target_index'] in (0,spec['targets']//2,spec['targets']-1) else None
                    row['native_event']=meta
            writer.event('native_events.jsonl',row)
        scene.drivers._receive=observed_receive
        save(directory/'job_spec.json',job);save(directory/'sensor_registry.json',scene.registry);save(directory/'render_profile.json',scene.render_actual)
        save(directory/'asset_manifest.json',scene.asset_manifest)
        save(directory/'source_manifest.json',{'original_v06':[{'path':str(p.relative_to(V06)),'sha256':digest(p)} for p in (V06/'sensor_visualizer_v06').rglob('*.py')],
            'adapter':[{'path':p.name,'sha256':digest(p)} for p in (PROJECT/'tools/experiments').glob('*.py')]})
        import carb.settings
        keys=['/rtx/hydra/supportMultiTickRate','/rtx/rendering/perSensorTickTlas','/renderer/raytracingMotion/enabled','/app/asyncRendering']
        save(directory/'effective_settings.json',{k:carb.settings.get_settings().get(k) for k in keys})
        pipeline=RecordPipeline(V06,directory,job,scene.registry,scene.render_actual,scene.capture_id,diagnostics);await pipeline.start()
        for entry in trajectory['entries']:
            current=entry['target']
            if current is None:raise RuntimeError('Missing C actual state: target '+str(entry['target_index']))
            group=current['target_index'];scene.drivers.set_capture_active(True)
            await scene.advance_clock(current['snapshot']['t_sim_s']);scene.apply_snapshot(current['snapshot'])
            actual=actual_state();qualification=equivalence(current,actual)
            writer.event('applied_states.jsonl',{'target_index':group,'source_epoch':current['source_epoch'],'physical_step':current['physical_step'],
                'frozen_native_time_ns':str(round(scene.native_time()*1e9)),'actual':actual,'input_equivalence':qualification})
            if not qualification['passed']:raise RuntimeError('Frozen input fails qualification for target '+str(group))
            arrays,bundle=await scene.capture(group,round(scene.native_time()*1e9))
            after=equivalence(current,actual_state());writer.event('capture_results.jsonl',{'target_index':group,'passed_original_validation':True,
                'input_equivalence_after':after,'bundle':{k:v for k,v in bundle.items() if k!='buffer'}})
            if not after['passed']:raise RuntimeError('Frozen actual input changed during warmup/capture')
            bundle['trajectory']={'snapshot_id':current['snapshot']['snapshot_id'],'source_session_id':current['source_epoch'],
                'trajectory_time_s':current['snapshot']['t_sim_s'],'native_epoch_ns':scene.epoch_ns,
                'time_quantization_error_s':(round(scene.native_time()*1e9)-scene.epoch_ns)/1e9-current['snapshot']['t_sim_s'],
                'source_state_revision':current['actual_state']['state_revision'],'source_mount_revision':current['snapshot']['mount_revision'],
                'mode':'explicit_pair','source_target_step':current['physical_step']}
            slot=await pipeline.reserve(group);await pipeline.submit(slot,arrays,bundle);report['written_groups']+=1
            if time.monotonic()>deadline:raise RuntimeError('Frozen wall budget exceeded')
        await scene.drivers.finish_generation();await pipeline.finish()
        report.update(status='EXPERIMENT_COMPLETE',written_groups=pipeline.written,pair_input_equivalence_ok=True)
    except Exception as exc:report.update(failure=str(exc),traceback=traceback.format_exc())
    finally:
        current=None
        if pipeline:
            try:
                if report['written_groups'] and not pipeline.finished:await pipeline.finish()
            except Exception as exc:report['drain_error']=str(exc)
            await pipeline.close()
        try:await scene.close();report['cleanup_ok']=True
        except Exception as exc:report.update(cleanup_ok=False,cleanup_error=str(exc))
        diagnostics.close();save(directory/'run_result.json',report)
        try:await asyncio.to_thread(writer.close)
        except Exception as exc:report.update(status='EXPERIMENT_FAILED',save_error=str(exc))
        save(parent/'frozen_terminal.json',report);print('[PAIRED F] '+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_uncancellable_quit(0 if report['status']=='EXPERIMENT_COMPLETE' else 2)

asyncio.ensure_future(run())
