"""Explicit, shared frozen-time rendering for cameras and Instant RTX LiDARs."""
import numpy as np


class StaleSample(RuntimeError):
    """A render product has not caught up to this frozen sample yet."""

def host(value):
    return value.numpy() if hasattr(value,'numpy') else np.asarray(value)


class SensorDrivers:
    def __init__(self, stage, layer, registry):
        import omni.replicator.core as rep
        from pxr import Usd
        self.rep, self.stage, self.registry = rep, stage, registry
        self.products = []; self.annotators = []; self.readers = {}
        self.camera_products = []
        self.lidar_products = []
        self.writers=[]; self.snapshots={}; self.errors={}; self.armed=False
        self.closed = False
        owner=self
        class SnapshotWriter(rep.Writer):
            version='2.0.0'
            _version='2.0.0'
            def __init__(self,kind,entry,annotators):
                self.version='2.0.0'
                self.kind,self.entry=kind,entry
                self.annotators=annotators
            def write(self,data):
                if owner.armed: owner._receive(self.kind,self.entry,data)
            def write_metadata(self): pass
        try:
            for kind in ('cameras', 'lidars'):
                for entry in registry[kind]:
                    sid = entry['id']
                    size = (entry['calibration']['width'], entry['calibration']['height']) if kind == 'cameras' else (300,300)
                    with Usd.EditContext(stage, layer):
                        product = rep.create.render_product(entry['prim_path'], size, name='SV02_'+sid,
                                                           force_new=True, write_to_session_layer=False)
                    self.products.append(product)
                    if kind=='cameras': self.camera_products.append(product)
                    else: self.lidar_products.append(product)
                    readers = {}
                    names = ('rgb','CameraParams','IsaacReadSimulationTime') if kind == 'cameras' else ('IsaacExtractRTXSensorPointCloud','IsaacReadSimulationTime')
                    for name in names:
                        # This Isaac build's generic cache is cleared by absent optional
                        # LiDAR arrays. Keep native views only until immediate .numpy().
                        annot = rep.AnnotatorRegistry.get_annotator(name,
                            device='cuda' if name in ('rgb','IsaacExtractRTXSensorPointCloud') else 'cpu',
                            do_array_copy=name!='IsaacExtractRTXSensorPointCloud')
                        if name == 'IsaacReadSimulationTime': annot.initialize(resetOnStop=True)
                        readers[name] = annot
                    self.readers[(kind, sid)] = readers
                    if kind=='cameras':
                        writer=SnapshotWriter(kind,entry,list(readers.values()))
                        writer.attach([product.path]); self.writers.append(writer)
                    else:
                        for annot in readers.values():
                            annot.attach([product.path]); self.annotators.append((annot,product.path))
        except Exception:
            self.detach()
            self.destroy()
            raise

    def enabled(self, value):
        for product in self.camera_products:
            product.hydra_texture.set_updates_enabled(value)

    async def render(self, subframes):
        self.enabled(True)
        self.snapshots={}; self.errors={}; self.armed=True
        try:
            await self.rep.orchestrator.step_async(delta_time=0.0, pause_timeline=True,
                                                   wait_for_render=True, rt_subframes=subframes)
        finally: self.armed=False

    async def warm_cameras(self, subframes):
        # No LiDAR array is consumed across this disable/enable boundary.
        # The subsequent all-sensor render must create fresh validated output.
        for product in self.lidar_products: product.hydra_texture.set_updates_enabled(False)
        try:
            await self.render(subframes)
        finally:
            for product in self.lidar_products: product.hydra_texture.set_updates_enabled(True)

    def _receive(self,kind,entry,data):
        key=(kind,entry['id'])
        def fetch(name):
            return next((v for k,v in data.items() if k==name or k.startswith(name+'-')),None)
        try:
            timing=fetch('IsaacReadSimulationTime')
            result={'IsaacReadSimulationTime':{'simulationTime':float(timing['simulationTime'])}}
            if kind=='cameras':
                value=fetch('rgb')
                if isinstance(value,dict): value=value['data']
                result['rgb']=host(value).copy()
                params=fetch('CameraParams')
                result['CameraParams']={'cameraViewTransform':np.asarray(params['cameraViewTransform']).copy(),
                                        'cameraModel':str(params.get('cameraModel',''))}
            self.snapshots[key]=result; self.errors.pop(key,None)
        except Exception as exc: self.errors[key]=str(exc)

    def read(self, stamp_ns, kinds=('cameras','lidars')):
        from pxr import Usd, UsdGeom
        arrays, cameras, lidars = {}, {}, {}
        cache = UsdGeom.XformCache(Usd.TimeCode.Default())
        for kind in kinds:
            for entry in self.registry[kind]:
                sid = entry['id']; key=(kind,sid)
                if kind=='lidars':
                    annotations=self.readers[key]
                    cloud=annotations['IsaacExtractRTXSensorPointCloud'].get_data()
                    # XYZ is the extractor-owned contiguous result. Its auxiliary
                    # pointer views are intentionally never read or retained.
                    self.snapshots[key]={'IsaacReadSimulationTime':annotations['IsaacReadSimulationTime'].get_data(),
                        'IsaacExtractRTXSensorPointCloud':{'data':host(cloud['data']).copy(),
                            'info':{'transform':np.asarray(cloud['info']['transform']).copy()}}}
                if key in self.errors: raise RuntimeError(sid+': snapshot callback: '+self.errors[key])
                if key not in self.snapshots: raise StaleSample('No render completion snapshot for '+sid)
                readers=self.snapshots[key]
                source = readers['IsaacReadSimulationTime']
                source_time = float(source['simulationTime'])
                if abs(round(source_time*1e9)-stamp_ns) > 2:
                    raise StaleSample(f'{sid}: source clock {source_time} does not match sample {stamp_ns}')
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
                    if error > 2e-3: raise StaleSample(f'{sid}: rendered camera pose differs from USD ({error})')
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
                        raise StaleSample(f'{sid}: rendered LiDAR pose differs from USD ({error})')
                    if not np.isfinite(points).all(): raise RuntimeError('Non-finite XYZ '+sid)
                    packed = np.asarray(points,dtype='<f4',order='C')
                    arrays['lidar/'+sid] = packed
                    lidars[sid] = {'to_world':authored.tolist(), 'source_time_s':source_time,
                                   'render_pose_max_abs_error':error, 'points':len(points),
                                   'coordinates':'sensor-local Cartesian metres','fields':['x','y','z']}
        return arrays, cameras, lidars

    def detach(self):
        self.armed=False
        for writer in reversed(self.writers): writer.detach()
        for annot,path in reversed(self.annotators): annot.detach([path])
        self.writers.clear(); self.snapshots.clear()
        self.annotators.clear(); self.readers.clear()

    def destroy(self):
        if self.closed: return
        for product in reversed(self.products): product.destroy()
        self.products.clear(); self.closed = True
