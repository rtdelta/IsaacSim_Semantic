"""Frozen rendering, serialized manual dispatch and owned snapshots."""
import asyncio
import numpy as np
from .diagnostics import NullDiagnostics
from .gating import ProductGate
from .tickets import SampleError

def host(value): return value.numpy() if hasattr(value,'numpy') else np.asarray(value)

class SensorDrivers:
    @classmethod
    async def create(cls,stage,layer,registry,diagnostics,generation,app,check_stage,backend='compatibility'):
        self=cls()
        self.backend=backend
        await self._initialize(stage,layer,registry,diagnostics,generation,app,check_stage)
        return self

    async def _initialize(self, stage, layer, registry, diagnostics=None, generation=None,app=None,check_stage=None):
        import omni.replicator.core as rep
        from pxr import Usd
        self.rep,self.stage,self.registry=rep,stage,registry
        self.diag=diagnostics or NullDiagnostics(); self.generation=generation
        self.products=[]; self.annotators=[]; self.readers={}; self.writers=[]
        self.snapshots={}; self.errors={}; self.ticket=None; self.inflight=None; self.closed=False
        self.generation_open=False
        self.capture_active=False;self.resource_policy='gated'
        self.gate=ProductGate(self.diag); self.progress=None
        owner=self
        class SnapshotWriter(rep.Writer):
            version='3.0.0'
            _version='3.0.0'
            def __init__(self,kind,entry,annotators):
                self.version='3.0.0'; self.kind,self.entry=kind,entry
                self.annotators=annotators; self.pending=None
            def write(self,data): owner._receive(self,data)
            def write_metadata(self): pass
        if not callable(getattr(rep.Writer,'schedule_write',None)):
            raise RuntimeError('Manual Writer.schedule_write unavailable; ambiguous dispatch refused')
        try:
            for kind in ('cameras','lidars'):
                for entry in registry[kind]:
                    sid=entry['id']; size=(entry['calibration']['width'],entry['calibration']['height']) if kind=='cameras' else (300,300)
                    with self.diag.span('product_create',sensor_id=kind+'/'+sid):
                        with Usd.EditContext(stage,layer):
                            product=rep.create.render_product(entry['prim_path'],size,name='SV06_'+sid,
                                                             force_new=True,write_to_session_layer=False)
                        self.products.append(product); self.gate.add(kind+'/'+sid,product)
                    readers={}
                    names=('rgb','CameraParams','IsaacReadSimulationTime') if kind=='cameras' else ('IsaacExtractRTXSensorPointCloud','IsaacReadSimulationTime')
                    with self.diag.span('annotators_attach',sensor_id=kind+'/'+sid):
                        for name in names:
                            annot=rep.AnnotatorRegistry.get_annotator(name,
                                device='cuda' if name in ('rgb','IsaacExtractRTXSensorPointCloud') else 'cpu',
                                do_array_copy=name!='IsaacExtractRTXSensorPointCloud')
                            if name=='IsaacReadSimulationTime': annot.initialize(resetOnStop=True)
                            readers[name]=annot
                        self.readers[(kind,sid)]=readers
                        if kind=='cameras' or self.backend=='persistent_gated':
                            writer=SnapshotWriter(kind,entry,list(readers.values()))
                            self.writers.append(writer); writer.attach([product.path],trigger=None)
                        else:
                            for annot in readers.values():
                                annot.attach([product.path]); self.annotators.append((annot,product.path))
                    if app:
                        await self._native(app.next_update_async(),'init_product_update')
                        if check_stage:check_stage()
            self.diag.set_manifest(sensor_capabilities={'backend':self.backend,'writer_manual_trigger':True,
                'completion_barrier':('render completion plus all-sensor owned manual receipts' if self.backend=='persistent_gated'
                                      else 'camera receipts plus Replicator stop/drain'),
                'source_frame_id':'not exposed by adapter; null, never synthesized',
                'lidar_readiness':('manual dispatch, independent host copy, source clock and RTX pose' if self.backend=='persistent_gated'
                                   else 'render and stop/drain plus source clock and RTX pose')})
        except BaseException:
            self.detach(); self.destroy(); raise

    def set_capture_active(self,active):
        self.capture_active=bool(active)
        if not active:self.gate.all(False,'session_inactive')
    def suspend_all(self,reason):
        boundaries={'group_boundary','advance','idle','camera_warmup_start','camera_warmup_complete',
                    'owned_payload_or_failed','capture_boundary'}
        healthy=not (reason=='owned_payload_or_failed' and self.ticket and not self.ticket.complete)
        if (getattr(self,'capture_active',False) and getattr(self,'resource_policy','gated')=='keepalive'
                and reason in boundaries and healthy):
            self.diag.event('sensor_resources_retained',reason=reason,
                observation='Actual updates remain enabled; intermediate motion renders are discarded')
        else:self.gate.all(False,reason)
    def set_updates(self,sensor_ids,enabled,reason): self.gate.set(sensor_ids,enabled,reason)
    def set_camera_updates(self,enabled,reason): self.gate.kind('cameras',enabled,reason)
    def set_lidar_updates(self,enabled,reason): self.gate.kind('lidars',enabled,reason)

    async def _native(self,operation,name):
        if self.inflight is not None: raise RuntimeError('Overlapping native operation')
        self.inflight=asyncio.ensure_future(operation)
        try:
            with self.diag.span(name):
                try: return await asyncio.shield(self.inflight)
                except asyncio.CancelledError:
                    self.diag.event('cancel_waiting_native',critical=True)
                    await asyncio.shield(self.inflight)
                    raise
        finally: self.inflight=None

    async def _step(self,subframes,reason):
        self.diag.event('render_submit',subframes=subframes,reason=reason,delta_time=0.0)
        self.generation_open=True
        await self._native(self.rep.orchestrator.step_async(delta_time=0.0,pause_timeline=True,
                           wait_for_render=True,rt_subframes=subframes),'render_wait')
        self.diag.event('render_return',reason=reason)

    async def render(self,subframes):
        """Initialization/mount settling: no formal Writer requests or image copies."""
        self.gate.all(True,'initialization_warmup')
        try:
            await self._step(subframes,'initialization_warmup')
            await self._drain_generation()
        finally: self.suspend_all('warmup_complete')

    async def warm_cameras(self,subframes,retain_generation=False):
        retain_generation=retain_generation or getattr(self,'backend','compatibility')=='persistent_gated'
        self.suspend_all('camera_warmup_start')
        # A generation started with only cameras leaves RTX LiDAR transforms
        # stale when added to that generation. Prime all selected sensors while
        # the same pose is frozen, then submit the formal request without a stop.
        if retain_generation:self.gate.all(True,'frozen_sensor_warmup')
        else:self.set_camera_updates(True,'camera_warmup')
        completed=False
        try:
            await self._step(subframes,'camera_warmup')
            if not retain_generation:await self._drain_generation()
            completed=True
            if retain_generation:
                self.diag.event('warmup_generation_retained',
                    boundary='all sensors primed at same frozen pose and clock; formal capture requires every owned receipt')
        finally:
            if not retain_generation or not completed:self.suspend_all('camera_warmup_complete')

    async def _drain_generation(self):
        # This STOPS generation/restores settings, not a cheap per-frame fence.
        # Compatibility polls LiDAR only after this SDK lifecycle boundary.
        # Persistent capture uses all-sensor receipts and stops only on quiesce.
        await self._native(self.rep.orchestrator.wait_until_complete_async(),'replicator_stop_drain')
        self.generation_open=False

    async def finish_generation(self):
        """Lifecycle stop only at pause/end/cleanup, after payload ownership."""
        self.capture_active=False
        self.suspend_all('quiesce')
        if getattr(self,'generation_open',False):await self._drain_generation()

    async def acquire(self,ticket,subframes,app,assert_scene,max_progress_updates):
        if self.ticket and self.ticket.open: raise RuntimeError('Previous ticket is open')
        if any(w.pending for w in self.writers):
            raise SampleError('callback_missing','Previous write not delivered; reinitialize required')
        self.ticket=ticket; self.snapshots={}; self.errors={}
        self.diag.context(**ticket.identity(),simulation_time_ns=ticket.expected_sim_ns)
        self.diag.event('ticket_open',expected=sorted(ticket.expected))
        self.gate.all(True,'formal_capture'); ticket.submitted=True
        try:
            for writer in self.writers:
                writer.pending=ticket; writer.schedule_write()
            await self._step(subframes,'formal_capture')
            ticket.render_complete=True; assert_scene()
            receipt_keys=(ticket.expected if getattr(self,'backend','compatibility')=='persistent_gated'
                          else {'cameras/'+c['id'] for c in self.registry['cameras']})
            updates=0
            while not receipt_keys.issubset(ticket.received):
                if ticket.errors: raise SampleError('payload_invalid',str(ticket.errors))
                if ticket.expired or updates>=max_progress_updates:
                    raise SampleError('capture_ready_timeout','Pending receipts: '+str(sorted(receipt_keys-ticket.received.keys())))
                if self.progress: self.progress(sorted(receipt_keys-ticket.received.keys()))
                await asyncio.sleep(0)
                if receipt_keys.issubset(ticket.received): break
                # Engine progress can render. Log it as such, not as a free wait.
                with self.diag.span('ready_progress_update',may_render=True):
                    await self._native(app.next_update_async(),'kit_ready_update')
                updates+=1; assert_scene()
            # Every scheduled Writer has returned its owned payload. No other
            # request can be scheduled until this ticket closes.
            if any(w.pending is not None for w in self.writers):
                raise SampleError('callback_missing','Manual dispatch not fully delivered')
            self.diag.event('writer_dispatch_complete',evidence='all scheduled callbacks received')
            if getattr(self,'backend','compatibility')=='compatibility':await self._drain_generation()
            else:self.diag.event('sensor_completion_barrier',evidence='render returned and all owned manual receipts received',**ticket.identity())
            assert_scene()
            with self.diag.span('readback_validation'): result=self.read(ticket.expected_sim_ns)
            assert_scene()
            self.diag.event('ticket_complete',critical=True,pending=ticket.pending,progress_updates=updates)
            return result
        except SampleError as exc:
            self.diag.warning(exc.reason,str(exc),sensor_id=exc.sensor_id); raise
        except Exception as exc:
            self.diag.warning('payload_invalid',str(exc))
            raise SampleError('payload_invalid',str(exc)) from exc
        finally:
            ticket.close(); self.suspend_all('owned_payload_or_failed')

    def _copy_host(self,value,sensor):
        if not hasattr(self,'array_interfaces'):self.array_interfaces=set()
        if sensor not in self.array_interfaces:
            self.array_interfaces.add(sensor)
            self.diag.event('producer_array_interface',sensor_id=sensor,type=type(value).__module__+'.'+type(value).__name__,
                producer_device=str(getattr(value,'device','not_exposed')),shape=list(getattr(value,'shape',())),
                transfer_interface='numpy()' if hasattr(value,'numpy') else 'numpy.asarray',
                ownership='SDK-owned input -> materialized host view -> independent CPU copy -> mmap slot')
        with self.diag.span('host_materialize',sensor_id=sensor,
                            measurement_source='host elapsed includes GPU wait, not pure DMA'):
            materialized=host(value)
        with self.diag.span('cpu_owned_copy',sensor_id=sensor,bytes=int(materialized.nbytes)):
            result=materialized.copy()
        self.diag.event('owned_array',sensor_id=sensor,bytes=int(result.nbytes),detail=True)
        return result

    def _receive(self,writer,data):
        sensor=writer.kind+'/'+writer.entry['id']; ticket=writer.pending
        self.diag.event('callback_received',sensor_id=sensor,request_id=ticket.request_id if ticket else None)
        if ticket is None or not ticket.open:
            self.diag.warning('callback_rejected_window_closed','Unscheduled/late callback',sensor_id=sensor); return
        writer.pending=None
        def fetch(name): return next((v for k,v in data.items() if k==name or k.startswith(name+'-')),None)
        try:
            timing=fetch('IsaacReadSimulationTime')
            result={'IsaacReadSimulationTime':{'simulationTime':float(timing['simulationTime'])}}
            if writer.kind=='cameras':
                value=fetch('rgb')
                if isinstance(value,dict):value=value['data']
                params=fetch('CameraParams')
                result.update(rgb=self._copy_host(value,sensor),
                    CameraParams={'cameraViewTransform':np.asarray(params['cameraViewTransform']).copy(),
                                  'cameraModel':str(params.get('cameraModel',''))})
            else:
                cloud=fetch('IsaacExtractRTXSensorPointCloud')
                result['IsaacExtractRTXSensorPointCloud']={'data':self._copy_host(cloud['data'],sensor),
                    'info':{'transform':np.asarray(cloud['info']['transform']).copy()}}
            ticket.receive(sensor,result,self.generation,ticket.request_id)
            self.snapshots[(writer.kind,writer.entry['id'])]=result
            self.diag.event('callback_accepted',sensor_id=sensor,**ticket.identity())
        except Exception as exc:
            ticket.errors[sensor]=str(exc); self.diag.warning('payload_invalid',str(exc),sensor_id=sensor)

    def read(self, stamp_ns, kinds=('cameras','lidars')):
        from pxr import Usd, UsdGeom
        arrays, cameras, lidars = {}, {}, {}
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        for kind in kinds:
            for entry in self.registry[kind]:
                sid = entry['id']; key=(kind,sid)
                if kind=='lidars' and getattr(self,'backend','compatibility')=='compatibility':
                    annotations=self.readers[key]
                    with self.diag.span('lidar_get_data',sensor_id='lidars/'+sid):
                        cloud=annotations['IsaacExtractRTXSensorPointCloud'].get_data()
                    # XYZ is the extractor-owned contiguous result. Its auxiliary
                    # pointer views are intentionally never read or retained.
                    self.snapshots[key]={'IsaacReadSimulationTime':annotations['IsaacReadSimulationTime'].get_data(),
                        'IsaacExtractRTXSensorPointCloud':{'data':self._copy_host(cloud['data'],'lidars/'+sid),
                            'info':{'transform':np.asarray(cloud['info']['transform']).copy()}}}
                    self.ticket.receive('lidars/'+sid,self.snapshots[key],self.generation,self.ticket.request_id)
                if key in self.errors: raise RuntimeError(sid+': snapshot callback: '+self.errors[key])
                if key not in self.snapshots: raise SampleError('callback_missing','No completion snapshot for '+sid,sid)
                readers=self.snapshots[key]
                source = readers['IsaacReadSimulationTime']
                source_time = float(source['simulationTime'])
                if abs(round(source_time*1e9)-stamp_ns) > 2:
                    raise SampleError('source_time_mismatch',f'{sid}: source clock {source_time} != {stamp_ns}',sid)
                authored = np.asarray(cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(entry['prim_path'])))
                if kind == 'cameras':
                    rgb = readers['rgb']
                    if isinstance(rgb, dict): rgb = rgb['data']
                    rgb = host(rgb)
                    cal = entry['calibration']
                    if rgb.shape[:2] != (cal['height'],cal['width']) or rgb.ndim != 3 or rgb.shape[2] not in (3,4) or rgb.dtype != np.uint8:
                        raise RuntimeError('Unexpected image layout for '+sid)
                    params = readers['CameraParams']
                    rendered = np.linalg.inv(np.asarray(params['cameraViewTransform']).reshape(4,4))
                    error = float(np.abs(rendered-authored).max())
                    if error > 2e-3: raise SampleError('render_pose_mismatch',f'{sid}: camera pose difference {error}',sid)
                    arrays['camera/'+sid] = rgb
                    cameras[sid] = {'to_world':authored.tolist(), 'source_time_s':source_time,
                                    'render_pose_max_abs_error':error,
                                    'legacy_camera_params_model':str(params.get('cameraModel',''))}
                else:
                    cloud = readers['IsaacExtractRTXSensorPointCloud']
                    if not isinstance(cloud,dict) or 'data' not in cloud: raise RuntimeError('Missing LiDAR result '+sid)
                    points = host(cloud['data']).reshape(-1,3)
                    rendered = np.asarray(cloud['info']['transform']).reshape(4,4)
                    error = float(np.abs(rendered-authored).max())
                    if error > 2e-3:
                        raise SampleError('render_pose_mismatch',f'{sid}: LiDAR pose difference {error}',sid)
                    if not np.isfinite(points).all(): raise RuntimeError('Non-finite XYZ '+sid)
                    packed = np.asarray(points,dtype='<f4',order='C')
                    arrays['lidar/'+sid] = packed
                    lidars[sid] = {'to_world':authored.tolist(), 'source_time_s':source_time,
                                   'render_pose_max_abs_error':error, 'points':len(points),
                                   'coordinates':'sensor-local Cartesian metres','fields':['x','y','z']}
                sensor_key=kind+'/'+sid
                evidence=('serialized_manual_writer' if kind=='cameras' or getattr(self,'backend','compatibility')=='persistent_gated'
                          else 'completed_render_poll')
                self.ticket.validate(sensor_key,round(source_time*1e9),error,evidence)
                meta=cameras[sid] if kind=='cameras' else lidars[sid]
                meta.update(source_frame_id=None, freshness_evidence=evidence)
                self.diag.event('payload_validated',sensor_id=sensor_key,source_simulation_time_ns=round(source_time*1e9),
                                source_frame_id=None, freshness_evidence=evidence, render_pose_max_abs_error=error,
                                **self.ticket.identity())
        if not self.ticket.complete: raise SampleError('payload_invalid','Ticket incomplete after validation')
        return arrays, cameras, lidars

    def detach(self):
        if self.inflight is not None: raise RuntimeError('Cannot detach during native work')
        if self.ticket: self.ticket.close()
        for writer in reversed(self.writers):
            try: writer.detach()
            except Exception as exc: self.diag.warning('resource_handle_invalid',str(exc),operation='writer_detach')
        for annot,path in reversed(self.annotators):
            try: annot.detach([path])
            except Exception as exc: self.diag.warning('resource_handle_invalid',str(exc),operation='annotator_detach')
        self.writers.clear(); self.snapshots.clear(); self.annotators.clear(); self.readers.clear()

    def destroy(self):
        if self.closed: return
        if self.inflight is not None: raise RuntimeError('Cannot destroy during native work')
        for product in reversed(self.products):
            try: product.destroy()
            except Exception as exc: self.diag.warning('resource_handle_invalid',str(exc),operation='product_destroy')
        self.products.clear(); self.gate.closed=True; self.closed=True
