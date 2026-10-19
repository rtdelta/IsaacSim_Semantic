"""In-memory instrumentation of the selected baseline; never edit installed SDK."""
import asyncio, ctypes, importlib, json, os, sys, threading, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads(Path(os.environ['SV04_EXPERIMENT_SPEC']).read_text())
PROJECT=ROOT.parent/SPEC['version']
sys.path.insert(0,str(PROJECT))
OUT=Path(SPEC['out'])
package='sensor_visualizer_'+SPEC['version']
print('[SV04 PROBE] Entry evaluated',flush=True)
(OUT/'entry_started.json').write_text(json.dumps({'at_ns':time.monotonic_ns(),'phase':'entry_evaluated'}))

async def main():
    print('[SV04 PROBE] Coroutine started',flush=True)
    (OUT/'entry_started.json').write_text(json.dumps({'at_ns':time.monotonic_ns(),'phase':'coroutine_started'}))
    import omni.kit.app, carb.settings
    from omni.replicator.core.scripts import orchestrator
    contracts=importlib.import_module(package+'.contracts')
    coordinator=importlib.import_module(package+'.coordinator')
    if SPEC.get('keep_lidar_alive') or SPEC.get('persistent_generation'):
        sensor_module=importlib.import_module(package+'.sensors')
        original_suspend=sensor_module.SensorDrivers.suspend_all
        def keep_lidar(self,reason):
            selected={'group_boundary','advance','idle','camera_warmup_start','camera_warmup_complete',
                      'owned_payload_or_failed','capture_boundary'}
            if reason in selected and self.diag.ctx.get('group_id') is not None and not SPEC.get('persistent_gates'):
                if not SPEC.get('persistent_generation'):self.gate.kind('cameras',False,reason)
                self.diag.event('diagnostic_lidar_keepalive',reason=reason,
                    observation='Persistent resources enabled during motion/warmup; intermediate data discarded')
            else:original_suspend(self,reason)
        sensor_module.SensorDrivers.suspend_all=keep_lidar
    if SPEC.get('persistent_generation'):
        original_drain=sensor_module.SensorDrivers._drain_generation
        async def no_group_drain(self):
            if self.diag.ctx.get('group_id') is not None and self.diag.ctx.get('phase') not in ('closing','failed','draining'):
                self.diag.event('diagnostic_drain_omitted',
                    evidence='step render completion and manual receipts; clock/pose validation remains strict')
                return
            await original_drain(self)
        sensor_module.SensorDrivers._drain_generation=no_group_drain
        scene_module=importlib.import_module(package+'.scene')
        original_advance=scene_module.SceneStepper.advance
        async def persistent_advance(self,group):
            self.timeline.set_auto_update(True)
            return await original_advance(self,group)
        scene_module.SceneStepper.advance=persistent_advance
    settings=carb.settings.get_settings()
    if SPEC.get('camera_only_warmup'):
        sensor_module=importlib.import_module(package+'.sensors')
        original_warm=sensor_module.SensorDrivers.warm_cameras
        async def camera_only_warm(self,subframes,retain_generation=False):
            self.gate.all(False,'diagnostic_camera_warmup')
            self.set_camera_updates(True,'diagnostic_camera_only')
            await self._step(subframes,'diagnostic_camera_only')
        sensor_module.SensorDrivers.warm_cameras=camera_only_warm
    if SPEC.get('split_sensor_warmup'):
        sensor_module=importlib.import_module(package+'.sensors')
        original_warm=sensor_module.SensorDrivers.warm_cameras
        async def split_sensor_warm(self,subframes,retain_generation=False):
            self.gate.all(True,'diagnostic_all_sensor_prime')
            await self._step(2,'diagnostic_sensor_pose_prime')
            self.set_lidar_updates(False,'diagnostic_camera_convergence')
            await self._step(subframes,'diagnostic_camera_convergence')
        sensor_module.SensorDrivers.warm_cameras=split_sensor_warm
    if SPEC.get('restore_capture_settings_before_formal'):
        sensor_module=importlib.import_module(package+'.sensors')
        original_step=sensor_module.SensorDrivers._step
        async def restore_before_formal(self,subframes,reason):
            if reason=='formal_capture':
                for name,value in (orchestrator._orchestrator._cached_settings or {}).items():
                    settings.set(name,value)
                self.diag.event('diagnostic_capture_settings_restored',
                    settings=orchestrator._orchestrator._cached_settings)
            return await original_step(self,subframes,reason)
        sensor_module.SensorDrivers._step=restore_before_formal
    if SPEC.get('diagnostic_repeat_frozen'):
        import numpy as np
        sensor_module=importlib.import_module(package+'.sensors')
        ticket_type=importlib.import_module(package+'.tickets').CaptureTicket
        original_acquire=sensor_module.SensorDrivers.acquire
        async def repeat_frozen(self,ticket,subframes,app,assert_scene,max_progress_updates):
            first=await original_acquire(self,ticket,subframes,app,assert_scene,max_progress_updates)
            if ticket.group_id==0:
                np.savez_compressed(OUT/'frozen_first.npz',**{k:v for k,v in first[0].items() if k.startswith('lidar/')})
                other=ticket_type(ticket.run_id,ticket.capture_id,ticket.group_id,ticket.stage_generation,
                    ticket.expected_sim_ns,ticket.pose_revision,ticket.expected,ticket.timeout_s)
                await self.warm_cameras(16)
                assert_scene()
                second=await original_acquire(self,other,subframes,app,assert_scene,max_progress_updates)
                assert_scene()
                np.savez_compressed(OUT/'frozen_repeat.npz',**{k:v for k,v in second[0].items() if k.startswith('lidar/')})
                (OUT/'frozen_repeat.json').write_text(json.dumps({'first_request_id':ticket.request_id,
                    'second_request_id':other.request_id,'simulation_ns':ticket.expected_sim_ns,
                    'both_complete':ticket.complete and other.complete,'first_lidars':first[2],'second_lidars':second[2],
                    'scope':'diagnostic re-render without motion or simulation advancement; not a throughput benchmark'}))
            return first
        sensor_module.SensorDrivers.acquire=repeat_frozen
    if SPEC.get('diagnostic_analytic_box'):
        sensor_module=importlib.import_module(package+'.sensors')
        original_sensor_initialize=sensor_module.SensorDrivers._initialize
        async def zero_noise_before_creation(self,stage,layer,registry,*args,**kwargs):
            from pxr import Usd
            with Usd.EditContext(stage,layer):
                for entry in registry['lidars']:
                    stage.GetPrimAtPath(entry['prim_path']).GetAttribute('omni:sensor:Core:rangeAccuracyM').Set(0.0)
            return await original_sensor_initialize(self,stage,layer,registry,*args,**kwargs)
        sensor_module.SensorDrivers._initialize=zero_noise_before_creation
    presentation_restore=None
    if SPEC.get('restore_scene_lights'):
        presentation_restore=orchestrator._orchestrator._set_capture_settings
        def preserve_lights():
            presentation_restore()
            settings.set('/app/viewport/show/lights',True)
        orchestrator._orchestrator._set_capture_settings=preserve_lights
    probe=[]; patches=[]; code=1; profile_range=None
    nvtx=ctypes.CDLL('/usr/local/cuda/lib64/libnvToolsExt.so.1') if SPEC.get('native') else None
    if nvtx:
        nvtx.nvtxRangePushA.argtypes=[ctypes.c_char_p];nvtx.nvtxRangePop.argtypes=[]
        nvtx.nvtxRangeStartA.argtypes=[ctypes.c_char_p];nvtx.nvtxRangeStartA.restype=ctypes.c_uint64
        nvtx.nvtxRangeEnd.argtypes=[ctypes.c_uint64]
    runner=None
    def state():
        return {'group_id':runner.diag.ctx.get('group_id') if runner else None,
                'phase':runner.phase if runner else None,'monotonic_ns':time.monotonic_ns(),
                'initMinLoadTime':settings.get('/exts/omni.replicator.core/initMinLoadTime'),
                'maxAssetLoadingTime':settings.get('/exts/omni.replicator.core/maxAssetLoadingTime')}
    def wrap_async(owner,name):
        original=getattr(owner,name)
        async def wrapped(*args,**kwargs):
            row={'sdk':name,'start':state()}; start=time.perf_counter()
            zone=nvtx.nvtxRangeStartA(('SV04 '+name+' g'+str(row['start']['group_id'])).encode()) if nvtx else None
            try:return await original(*args,**kwargs)
            finally:
                if zone is not None:nvtx.nvtxRangeEnd(zone)
                row.update(duration_s=time.perf_counter()-start,end=state());probe.append(row)
        setattr(owner,name,wrapped);patches.append((owner,name,original))
    wrap_async(orchestrator._orchestrator,'_initialize_async')
    for name in ('_next_render_update_async','step_async','stop_async','wait_until_complete_async'):
        wrap_async(orchestrator,name)
    try:
        job=contracts.load_job(SPEC['job'])
        runner=coordinator.CaptureRunner(PROJECT,job)
        def changed(r):
            nonlocal profile_range
            if SPEC.get('single_hdr_dome') and r.phase=='idle' and r.scene:
                from pxr import Usd
                with Usd.EditContext(r.scene.stage,r.scene.layer):
                    r.scene.stage.GetPrimAtPath('/World/UndulatingGround/env_light').SetActive(False)
                r.diag.event('diagnostic_single_hdr_dome',scope='runtime session layer only')
            if SPEC.get('diagnostic_analytic_box') and r.phase=='idle' and r.scene and not (OUT/'analytic_box.json').exists():
                import numpy as np
                from pxr import Usd,UsdGeom,Gf
                stage=r.scene.stage;hidden=[];cache=UsdGeom.XformCache()
                locations=[np.asarray(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(e['prim_path'])))[3,:3]
                    for e in r.scene.registry['lidars']]
                low=np.min(locations,axis=0)-3;high=np.max(locations,axis=0)+3
                with Usd.EditContext(stage,r.scene.layer):
                    for prim in list(stage.Traverse()):
                        if not prim:continue
                        if prim.IsA(UsdGeom.Gprim) or 'Gaussian' in str(prim.GetTypeName()):
                            prim.SetActive(False);hidden.append(str(prim.GetPath()))
                    cube=UsdGeom.Cube.Define(stage,'/World/SV04AnalyticTarget')
                    cube.CreateSizeAttr(2.0);cube.CreateDoubleSidedAttr(True)
                    x=UsdGeom.Xformable(cube);x.AddTranslateOp().Set(Gf.Vec3d(*((low+high)/2)))
                    x.AddScaleOp().Set(Gf.Vec3f(*((high-low)/2)))
                (OUT/'analytic_box.json').write_text(json.dumps({'min_world':low.tolist(),'max_world':high.tolist(),
                    'hidden_renderables':hidden,'range_accuracy_m':0,'scope':'diagnostic Session layer; no equal-quality speed claim'}))
            if SPEC.get('diagnostic_analytic_box') and r.phase=='advancing' and r.diag.ctx.get('group_id')==2:
                r.scene.drivers.resource_policy='keepalive'
                r.diag.event('diagnostic_policy_switch',policy='keepalive',scope='analytic geometry regression only')
            if SPEC.get('diagnostic_mesh_only') and r.phase=='idle' and r.scene and not (OUT/'mesh_only.json').exists():
                from pxr import Usd
                disabled=[]
                with Usd.EditContext(r.scene.stage,r.scene.layer):
                    for prim in list(r.scene.stage.Traverse()):
                        if 'Gaussian' in str(prim.GetTypeName()):
                            disabled.append(str(prim.GetPath()));prim.SetActive(False)
                    for entry in r.scene.registry['lidars']:
                        r.scene.stage.GetPrimAtPath(entry['prim_path']).GetAttribute('omni:sensor:Core:rangeAccuracyM').Set(0.0)
                (OUT/'mesh_only.json').write_text(json.dumps({'disabled_particle_fields':disabled,'range_accuracy_m':0,
                    'scope':'diagnostic Session layer only; changed content excluded from equal-quality performance claims'}))
            if r.phase=='idle' and r.scene and not (OUT/'scene_render_evidence.json').exists():
                from pxr import UsdGeom
                evidence=[]
                for prim in r.scene.stage.Traverse():
                    if prim.GetTypeName()=='DomeLight' or 'Gaussian' in str(prim.GetTypeName()):
                        attrs={a.GetName():str(a.Get())[:1024] for a in prim.GetAttributes()
                               if not str(a.GetTypeName()).endswith('[]')}
                        evidence.append({'path':str(prim.GetPath()),'type':str(prim.GetTypeName()),
                            'visibility':str(UsdGeom.Imageable(prim).ComputeVisibility()),'attributes':attrs})
                (OUT/'scene_render_evidence.json').write_text(json.dumps(evidence,indent=2))
            if nvtx and r.phase=='advancing' and r.diag.ctx.get('group_id')==SPEC.get('profile_first',1) and profile_range is None:
                nvtx.nvtxRangePushA(b'SV04_PROFILE');profile_range=True
                probe.append({'profile':'start',**state()})
            if profile_range is True and r.phase=='advancing' and r.diag.ctx.get('group_id')==SPEC.get('profile_last',3)+1:
                nvtx.nvtxRangePop();profile_range=False;probe.append({'profile':'end',**state()})
        runner.on_update=changed
        result=await runner.run()
        (OUT/'capture_result.json').write_text(json.dumps({'status':result,'session':str(runner.session)},indent=2))
        code=0 if result['state']=='finished' else 1
    except Exception:traceback.print_exc()
    finally:
        if profile_range is True:nvtx.nvtxRangePop()
        for owner,name,original in patches:setattr(owner,name,original)
        if presentation_restore:orchestrator._orchestrator._set_capture_settings=presentation_restore
        if SPEC.get('diagnostic_repeat_frozen'):sensor_module.SensorDrivers.acquire=original_acquire
        if SPEC.get('diagnostic_analytic_box'):sensor_module.SensorDrivers._initialize=original_sensor_initialize
        if SPEC.get('camera_only_warmup'):sensor_module.SensorDrivers.warm_cameras=original_warm
        if SPEC.get('split_sensor_warmup'):sensor_module.SensorDrivers.warm_cameras=original_warm
        if SPEC.get('restore_capture_settings_before_formal'):sensor_module.SensorDrivers._step=original_step
        if SPEC.get('keep_lidar_alive') or SPEC.get('persistent_generation'):sensor_module.SensorDrivers.suspend_all=original_suspend
        if SPEC.get('persistent_generation'):
            sensor_module.SensorDrivers._drain_generation=original_drain
            scene_module.SceneStepper.advance=original_advance
        (OUT/'sdk_probe.json').write_text(json.dumps(probe,indent=2))
        timer=threading.Timer(15,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)

_sv04_probe_task=asyncio.ensure_future(main())
def _failure(task):
    if not task.cancelled() and task.exception():
        traceback.print_exception(task.exception())
        (OUT/'entry_failure.json').write_text(json.dumps({'error':repr(task.exception())}))
        import omni.kit.app
        omni.kit.app.get_app().post_quit(1)
        timer=threading.Timer(15,lambda:os._exit(1));timer.daemon=True;timer.start()
_sv04_probe_task.add_done_callback(_failure)
