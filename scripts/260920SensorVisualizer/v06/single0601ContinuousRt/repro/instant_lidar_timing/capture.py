"""Ten-ray synthetic OmniLidar, six walls, one PRE write per 60 Hz physics step.

Run with launch.py. Capture only copies native data; geometry is evaluated after
the timeline stops. This file imports no application/project collection code.
"""
import asyncio
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
NAMES = ['IsaacExtractRTXSensorPointCloud', 'GenericModelOutput',
         'IsaacReadSimulationTime', 'ReferenceTime']
SETTINGS = {'/app/settings/fabricDefaultSimPeriodNumerator': 1,
            '/app/settings/fabricDefaultSimPeriodDenominator': 60,
            '/rtx/rendermode': 'RealTimePathTracing', '/rtx/post/dlss/execMode': 2,
            '/rtx/post/aa/op': 3, '/rtx-transient/dlssg/enabled': False,
            '/rtx/post/motionblur/enabled': False, '/rtx/hydra/supportMultiTickRate': True,
            '/rtx/rendering/perSensorTickTlas': True, '/app/asyncRendering': False,
            '/rtx/scenedb/maxHistoryTransformCount': 64}


def safe(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    try:
        return [safe(v) for v in value]
    except TypeError:
        return str(value)


def matrix(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return [[c, s, 0., 0.], [-s, c, 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


async def main():
    import carb.settings
    import omni.kit.app
    import omni.usd
    import omni.timeline
    import omni.replicator.core as rep
    import isaacsim.sensors.experimental.rtx
    from isaacsim.core.simulation_manager import SimulationManager as sm, SimulationEvent, _simulation_manager
    from isaacsim.core.rendering_manager import RenderingManager as rm
    from pxr import Gf, Sdf, Usd, UsdGeom
    from analyze import analyze

    spec = json.loads(Path(os.environ['LIDAR_REPRO_REQUEST']).read_text())
    out = Path(spec['output'])
    def save(name, data):
        (out / name).write_text(json.dumps(safe(data), indent=2, allow_nan=False))
    app, ctx = omni.kit.app.get_app(), omni.usd.get_context()
    tl, settings = omni.timeline.get_timeline_interface(), carb.settings.get_settings()
    mapper = _simulation_manager.acquire_simulation_manager_interface()
    states, events, updates, callbacks, calibration = [], [], [], [], []
    writer = product = pose = stage = None
    offset, pre, motion_start, observing, copied_bytes = None, None, None, False, 0
    callback_errors = []
    plan = []
    summary = {'capture_complete': False, 'measurement_qualified': False,
               'bug_confirmed': False, 'formal_continuous_acceptance': False}
    deadline = time.monotonic() + 540

    def on_pre(dt, context=None):
        nonlocal pre
        try:
            pre = sm.get_num_physics_steps()
            step = pre + (offset if offset is not None else 1)
            n = max(0, step - motion_start + 1) if motion_start is not None else 0
            pose.Set(Gf.Matrix4d(matrix(math.radians(n * spec['yaw_rate_deg_s'] / 60))))
        except Exception as exc:
            callback_errors.append(str(exc))

    def on_post(dt, context=None):
        try:
            step = sm.get_num_physics_steps()
            if offset is None:
                calibration.append(step - pre)
            m = safe(UsdGeom.Xformable(stage.GetPrimAtPath('/Lidar')).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
            states.append({'step': step, 'time_ns': round(sm.get_simulation_time() * 1e9),
                           'dt': float(dt), 'matrix': m, 'yaw_rad': math.atan2(m[0][1], m[0][0])})
        except Exception as exc:
            callback_errors.append(str(exc))

    class Capture(rep.Writer):
        version = '1.0.0'
        _version = '1.0.0'
        def __init__(self, annotators):
            self.annotators = annotators
        def write_metadata(self):
            pass
        def write(self, data):
            nonlocal copied_bytes
            if not observing:
                return
            try:
                def fetch(name):
                    matches = [v for k, v in data.items() if k == name or k.startswith(name + '-')]
                    if len(matches) != 1:
                        raise ValueError('Missing or ambiguous same-event ' + name)
                    return matches[0]
                gmo = fetch('GenericModelOutput')
                if isinstance(gmo, dict):
                    gmo = gmo['data']
                if hasattr(gmo, 'numpy'):
                    gmo = gmo.numpy()
                if not isinstance(gmo, np.ndarray) or gmo.dtype != np.uint8 or not 264 <= gmo.nbytes <= 1024 * 1024:
                    raise ValueError('Unexpected GMO layout/size for ten rays')
                raw = np.array(gmo, copy=True).tobytes()
                xyz = fetch('IsaacExtractRTXSensorPointCloud')['data']
                if hasattr(xyz, 'numpy'):
                    xyz = xyz.numpy()
                xyz = np.array(xyz, dtype=np.float32, copy=True).reshape(-1, 3)
                copied_bytes += len(raw) + xyz.nbytes
                if copied_bytes > 64 * 1024**2:
                    raise RuntimeError('Capture exceeded 64 MiB memory bound')
                source = fetch('IsaacReadSimulationTime')
                reference = fetch('ReferenceTime')
                num, den = int(reference['referenceTimeNumerator']), int(reference['referenceTimeDenominator'])
                if den <= 0:
                    raise ValueError('Invalid native reference time')
                mapped = mapper.get_simulation_time_at_time((num, den))
                events.append({'source_ns': round(float(source['simulationTime']) * 1e9),
                               'mapped_ns': round(float(mapped) * 1e9), 'reference': [num, den],
                               'receipt_step': sm.get_num_physics_steps(), 'raw': raw, 'xyz': xyz})
            except Exception as exc:
                callback_errors.append(str(exc))

    async def update(phase):
        before = sm.get_num_physics_steps()
        await app.next_update_async()
        updates.append({'phase': phase, 'before': before, 'after': sm.get_num_physics_steps()})
        if callback_errors:
            raise RuntimeError('; '.join(callback_errors))
        if time.monotonic() > deadline:
            raise TimeoutError('Bounded capture timeout')

    try:
        for k, v in SETTINGS.items():
            settings.set(k, v)
        settings.set('/renderer/raytracingMotion/enabled', spec['motion_bvh'])
        await ctx.new_stage_async()
        stage = ctx.get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        tl.stop()
        tl.commit()
        rep.orchestrator.set_capture_on_play(False)
        sensor = stage.DefinePrim('/Lidar', 'OmniLidar')
        sensor.SetMetadata('apiSchemas', Sdf.TokenListOp.CreateExplicit(['OmniSensorGenericLidarCoreAPI']))
        authored = json.loads((HERE / 'sensor.json').read_text())['attributes']
        for name, attr in authored.items():
            a = sensor.GetAttribute(name)
            if not a:
                a = sensor.CreateAttribute(name, Sdf.ValueTypeNames.Find(attr['usd_type']), custom=False)
            a.Set(attr['value'])
        pose = UsdGeom.Xformable(sensor).MakeMatrixXform()
        pose.Set(Gf.Matrix4d(1.))
        for axis, limit in ((0, -7.), (0, 10.), (1, -11.), (1, 8.), (2, -4.), (2, 6.)):
            wall = UsdGeom.Cube.Define(stage, '/Room/wall_%s_%s' % (axis, 'p' if limit > 0 else 'n'))
            wall.CreateSizeAttr(2.)
            m = np.eye(4)
            m[:3, :3] = np.diag([.01 if j == axis else 20. for j in range(3)])
            m[3, axis] = limit + math.copysign(.01, limit)
            wall.AddTransformOp().Set(Gf.Matrix4d(m.tolist()))
        sm.setup_simulation(dt=1/60)
        rm.set_dt(1/60)
        # Creating the stage/simulation can reset renderer options.
        for k, v in SETTINGS.items():
            settings.set(k, v)
        settings.set('/renderer/raytracingMotion/enabled', spec['motion_bvh'])
        callbacks.extend([sm.register_callback(on_pre, SimulationEvent.PHYSICS_PRE_STEP, order=-100),
                          sm.register_callback(on_post, SimulationEvent.PHYSICS_POST_STEP, order=100)])
        tl.play()
        tl.commit()
        for _ in range(6):
            await update('initialize')
        tl.pause()
        tl.commit()
        if len(set(calibration)) != 1 or calibration[0] not in (0, 1):
            raise RuntimeError('PRE/POST step indexing not qualified')
        offset = calibration[0]
        product = rep.create.render_product('/Lidar', (300, 300), name='TimingRepro', force_new=True)
        annotators = []
        for name in NAMES:
            a = rep.AnnotatorRegistry.get_annotator(name, device='cpu', do_array_copy=True)
            if name == 'IsaacReadSimulationTime':
                a.initialize(resetOnStop=True)
            annotators.append(a)
        writer = Capture(annotators)
        writer.attach([product.path])
        rep.orchestrator.set_capture_on_play(True)
        observing = True
        tl.play()
        tl.commit()
        for _ in range(24):
            await update('warmup')
        anchors = []
        for e in events:
            matches = [s for s in states if abs(s['time_ns'] - e['source_ns']) <= 2
                       and abs(s['time_ns'] - e['mapped_ns']) <= 2]
            if len(matches) == 1 and abs(e['source_ns'] - e['mapped_ns']) <= 2:
                anchors.append(matches[0]['step'])
        anchors = sorted(set(anchors))
        if len(anchors) < 2 or any(b-a != 6 for a, b in zip(anchors, anchors[1:])):
            raise RuntimeError('Warmup source events do not qualify as 10 Hz')
        current = sm.get_num_physics_steps()
        first = anchors[-1] + ((current-anchors[-1])//6 + 2)*6
        motion_start = first - 5
        plan = list(range(first, first + 6*spec['targets'], 6))
        save('plan.json', {'targets': plan, 'motion_start': motion_start, 'end': plan[-1]+12,
                           'warmup_anchor_steps': anchors, 'pre_post_offset': offset})
        effective = {name: safe(sensor.GetAttribute(name).Get()) for name in authored}
        save('effective_sensor.json', effective)
        if any(effective[name] != attr['value'] for name, attr in authored.items()):
            raise RuntimeError('Effective sensor attributes differ from authored values')
        requested = dict(SETTINGS, **{'/renderer/raytracingMotion/enabled': spec['motion_bvh']})
        actual = {k: safe(settings.get(k)) for k in requested}
        save('settings.json', {'requested': requested, 'effective': actual})
        if actual != requested:
            raise RuntimeError('Effective renderer settings differ from request')
        save('environment.json', {'isaac_sim': (Path(spec['isaac_root'])/'VERSION').read_text().strip(),
                                  'kit': app.get_build_version(), 'python': sys.version.split()[0],
                                  'headless': not spec['gui']})
        stage.GetRootLayer().Export(str(out / 'scene.usda'))
        while sm.get_num_physics_steps() < plan[-1] + 12:
            await update('motion_and_drain')
        summary['capture_complete'] = True
    except Exception as exc:
        summary.update(error=str(exc), traceback=traceback.format_exc())
    finally:
        observing = False
        try:
            tl.pause()
            tl.commit()
            if writer:
                writer.detach()
            rep.orchestrator.set_capture_on_play(False)
            await asyncio.wait_for(rep.orchestrator.stop_async(), 15)
            if product:
                product.destroy()
            for callback in callbacks:
                sm.deregister_callback(callback)
            tl.stop()
            tl.commit()
            summary['cleanup_ok'] = True
        except Exception as exc:
            summary.update(cleanup_ok=False, cleanup_error=str(exc))
        save('physics.json', states)
        save('updates.json', updates)
        save('callback_errors.json', callback_errors)
        serial = []
        for index, event in enumerate(events):
            raw = event['raw']
            path = 'gmo_%04d.bin.gz' % index
            (out / path).write_bytes(gzip.compress(raw, mtime=0))
            serial.append({**{k: v for k, v in event.items() if k not in ('raw', 'xyz')},
                           'path': path, 'sha256_uncompressed': hashlib.sha256(raw).hexdigest(),
                           'extractor_xyz': event['xyz'].tolist()})
        save('events.json', serial)
        if summary['capture_complete'] and summary.get('cleanup_ok'):
            try:
                summary.update(analyze(out))
            except Exception as exc:
                summary.update(analysis_error=str(exc), traceback=traceback.format_exc())
        save('summary.json', summary)
        app.post_uncancellable_quit(0 if summary['measurement_qualified'] else 2)


asyncio.ensure_future(main())
