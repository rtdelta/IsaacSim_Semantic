"""Long-lived native writers. Independent CPU data is copied inside write()."""
import time
import numpy as np
from .common import ContractError, source_ns


def pose_error(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    translation = float(np.linalg.norm(a[3, :3] - b[3, :3]))
    # atan2 avoids the artificial rotation error of acos near identity.
    r = a[:3, :3] @ b[:3, :3].T
    sine = np.linalg.norm([r[2,1]-r[1,2], r[0,2]-r[2,0], r[1,0]-r[0,1]]) / 2
    angle = float(np.arctan2(sine, (np.trace(r) - 1) / 2))
    return translation, abs(angle)


class ContinuousBackend:
    def __init__(self, stage, layer, registry, receive, reject, capability_id, native_trace=False):
        import omni.replicator.core as rep
        from isaacsim.core.simulation_manager import _simulation_manager
        from pxr import Usd
        self.rep, self.registry = rep, registry
        self.iface = _simulation_manager.acquire_simulation_manager_interface()
        self.receive, self.reject = receive, reject
        self.capability_id = capability_id
        self.products, self.writers = [], []
        self.sequence = 0
        self.permit = lambda mapped_ns: True
        self.updates_enabled=True
        self.native_adapter=None
        self.on_native_packet=lambda evidence,packet:None
        if native_trace:
            from .native_event import NativeEventAdapter
            self.native_adapter=NativeEventAdapter()
        owner = self
        class EventWriter(rep.Writer):
            version = '1.0.0'
            _version = '1.0.0'
            def __init__(self, entry, kind, annotations):
                self.entry, self.kind, self.annotators = entry, kind, annotations
                self.version = '1.0.0'
            def write(self, data):
                owner._receive(self, data)
            def write_metadata(self):
                pass
        try:
            for kind, entries in (('camera', registry['cameras']), ('lidar', registry['lidars'])):
                for entry in entries:
                    size = (1920, 1080) if kind == 'camera' else (300, 300)
                    with Usd.EditContext(stage, layer):
                        product = rep.create.render_product(entry.get('render_prim_path',entry['prim_path']), size, name='S0601_' + entry['id'],
                                                            force_new=True, write_to_session_layer=False)
                    self.products.append(product)
                    names = ['rgb', 'CameraParams'] if kind == 'camera' else ['IsaacExtractRTXSensorPointCloud']
                    if kind=='lidar' and self.native_adapter:
                        names.append('GenericModelOutput')
                    names += ['IsaacReadSimulationTime', 'ReferenceTime']
                    annotations = []
                    for name in names:
                        annot = rep.AnnotatorRegistry.get_annotator(name, device='cpu', do_array_copy=True)
                        if name == 'IsaacReadSimulationTime':
                            annot.initialize(resetOnStop=True)
                        annotations.append(annot)
                    writer = EventWriter(entry, kind, annotations)
                    writer.product_path = product.path
                    self.writers.append(writer)
                    writer.attach([product.path])
        except Exception:
            self.close()
            raise

    def _receive(self, writer, data):
        received = time.monotonic_ns()
        seq, self.sequence = self.sequence, self.sequence + 1
        def fetch(name):
            matches = [v for k, v in data.items() if k == name or k.startswith(name + '-')]
            if len(matches) != 1:
                raise ContractError('annotator_missing', name + ': expected one same-event value; keys=' + str(list(data)))
            return matches[0]
        try:
            ref, timing = fetch('ReferenceTime'), fetch('IsaacReadSimulationTime')
            numerator, denominator = int(ref['referenceTimeNumerator']), int(ref['referenceTimeDenominator'])
            if denominator <= 0:
                raise ContractError('native_reference', 'Invalid reference denominator')
            source = float(timing['simulationTime'])
            mapped = float(self.iface.get_simulation_time_at_time((numerator, denominator)))
            # Filter by the native render event's mapped time, before copying a payload.
            # A frozen physics boundary can emit cached annotators with another native reference.
            if not self.permit(source_ns(mapped)):
                return
            if abs(source_ns(mapped) - source_ns(source)) > 2:
                raise ContractError('source_mapping', 'Native reference mapping differs: annotator=%r mapped=%r ref=%s/%s' % (source, mapped, numerator, denominator))
            if writer.kind == 'camera':
                payload = fetch('rgb')
                if isinstance(payload, dict):
                    payload = payload['data']
                payload = payload.numpy() if hasattr(payload, 'numpy') else np.asarray(payload)
                producer_shape = list(payload.shape)
                if payload.dtype != np.uint8 or payload.shape[:2] != (1080, 1920) or payload.shape[2] not in (3, 4):
                    raise ContractError('image_layout', 'Native image does not match full-resolution RGB/RGBA contract')
                owned = np.array(payload[:, :, :3], dtype=np.uint8, order='C', copy=True)
                rendered = np.linalg.inv(np.asarray(fetch('CameraParams')['cameraViewTransform'], dtype=float).reshape(4, 4))
            else:
                cloud = fetch('IsaacExtractRTXSensorPointCloud')
                payload = cloud['data']
                payload = payload.numpy() if hasattr(payload, 'numpy') else np.asarray(payload)
                owned = np.array(payload.reshape(-1, 3), dtype='<f4', order='C', copy=True)
                producer_shape = list(payload.shape)
                if not np.isfinite(owned).all():
                    raise ContractError('nonfinite_points', 'Nonfinite point input is rejected without filtering')
                rendered = np.asarray(cloud['info']['transform'], dtype=float).reshape(4, 4).copy()
            evidence = {'sensor_id': writer.entry['sensor_id'], 'kind': writer.kind,
                'source_time_s': source, 'source_time_ns': str(source_ns(source)),
                'native_ref': {'kind': 'rational_time', 'scope': writer.product_path,
                               'numerator': str(numerator), 'denominator': str(denominator), 'event_id': None},
                'source_frame_id': None, 'receipt_seq': seq,
                'source_time_provenance': {'annotator': 'IsaacReadSimulationTime', 'clock_domain': 'physics_simulation',
                    'mapping_method': 'get_simulation_time_at_time(ReferenceTime) cross-check in the same Writer event', 'capability_id': self.capability_id},
                'received_monotonic_ns': str(received), 'copy_completed_monotonic_ns': str(time.monotonic_ns()),
                'rendered_to_world': rendered.tolist(), 'ownership': 'owned_cpu', 'shape': list(owned.shape),
                'dtype': 'uint8' if writer.kind == 'camera' else '<f4',
                'byte_order': 'not_applicable' if writer.kind == 'camera' else 'little', 'raw_nbytes': int(owned.nbytes),
                'producer_array_type': type(payload).__module__ + '.' + type(payload).__name__,
                'producer_device': str(getattr(payload, 'device', 'cpu'))}
            if writer.kind == 'camera':
                evidence['producer_shape'] = producer_shape
            else:
                evidence['points'] = len(owned)
                if self.native_adapter:
                    metadata,packet=self.native_adapter.capture(fetch('GenericModelOutput'))
                    evidence['native_event']=metadata
                    self.on_native_packet(evidence,packet)
            self.receive(evidence, owned)
        except Exception as exc:
            self.reject({'sensor_id': writer.entry['sensor_id'], 'receipt_seq': seq,
                         'code': getattr(exc, 'code', 'native_callback'), 'message': str(exc), 'keys': list(data)})

    def detach(self):
        for writer in self.writers:
            writer.detach()
        self.writers = []

    def set_updates(self,enabled):
        if self.updates_enabled==enabled:
            return
        for product in self.products:
            product.hydra_texture.set_updates_enabled(enabled)
        self.updates_enabled=enabled

    def close(self):
        self.detach()
        for product in self.products:
            product.destroy()
        self.writers, self.products = [], []


class BarrierBackend(ContinuousBackend):
    """Same owned callback path, manual request, exactly one target in flight."""
    def use_manual_triggers(self):
        for writer, product in zip(self.writers, self.products):
            writer.detach()
            writer.attach([product.path], trigger=None)

    def schedule(self):
        for writer in self.writers:
            writer.schedule_write()

    async def render_once(self):
        await self.rep.orchestrator.step_async(delta_time=0.0, pause_timeline=True, wait_for_render=False, rt_subframes=1)
