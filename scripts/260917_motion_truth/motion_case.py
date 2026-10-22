"""Capture full ray-time metadata against a translated analytic 20 m chamber."""
import argparse
import json
from pathlib import Path
import time
import traceback
p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
p.add_argument('--motion', choices=['static', 'sensor', 'target'], default='static')
p.add_argument('--bvh', type=int, choices=[0, 1], default=1)
p.add_argument('--compensated', type=int, choices=[0, 1], default=0)
p.add_argument('--reference', choices=['SENSOR', 'WORLD'], default='SENSOR')
p.add_argument('--speed', type=float, default=2.)
p.add_argument('--fps', type=int, default=60)
p.add_argument('--frames', type=int, default=180)
p.add_argument('--cycles', type=int, default=2)
p.add_argument('--driver', choices=['usd', 'configured', 'physics'], default='usd')
p.add_argument('--zero-delay', action='store_true')
p.add_argument('--pattern', choices=['rotary', 'fixed'], default='rotary')
p.add_argument('--accumulate', type=int, choices=[0, 1], default=1)
p.add_argument('--angular-speed', type=float, default=0., help='Sensor yaw velocity, degrees/s; physics driver only')
p.add_argument('--zero-damping', action='store_true')
a, _ = p.parse_known_args()
a.out.mkdir(parents=True, exist_ok=True)
r = {'args': {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()},
     'status': 'starting', 'samples': [], 'updates': [], 'stale': []}
def phase(name):
    r['phase'] = name
    (a.out/'progress.json').write_text(json.dumps(r, indent=2))
    print('TRUTH_PROBE', name, flush=True)
phase('starting_app')
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'multi_gpu': False, 'fast_shutdown': True,
    'width': 320, 'height': 240, 'limit_cpu_threads': 8,
    'extra_args': ['--/app/settings/loadUserConfig=false', '--/app/settings/persistent=false',
        '--/app/asyncRendering=false', '--/app/file/ignoreUnsavedOnExit=true',
        '--/app/player/useFixedTimeStepping=true', '--/app/player/useFastMode=false',
        '--/renderer/raytracingMotion/enabled=' + str(bool(a.bvh)).lower(),
        '--/renderer/raytracingMotion/enableHydraEngineMasking=false',
        '--/rtx/hydra/supportMultiTickRate=true', '--/rtx/rendering/perSensorTickTlas=true',
        '--/log/file=' + str(a.out/'kit.log')] +
        (['--/app/hydraEngine/waitIdle=true', '--/app/updateOrder/checkForHydraRenderComplete=1000'] if a.zero_delay else [])})
try:
    import numpy as np
    import carb.settings
    import omni.timeline
    import omni.usd
    import omni.replicator.core as rep
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, PhysxSchema
    from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
    from isaacsim.core.simulation_manager import SimulationManager
    from isaacsim.core.rendering_manager import RenderingManager
    settings = carb.settings.get_settings()
    settings.set('/app/player/timeCodesPerSecond', float(a.fps))
    r['settings'] = {k: settings.get(k) for k in ['/renderer/raytracingMotion/enabled',
        '/rtx/hydra/supportMultiTickRate', '/rtx/rendering/perSensorTickTlas', '/app/player/timeCodesPerSecond']}
    ctx = omni.usd.get_context()
    if a.driver in ['configured', 'physics']:
        RenderingManager.set_dt(1./a.fps)
    ctx.new_stage()
    stage = ctx.get_stage()
    stage.SetEditTarget(stage.GetRootLayer())
    stage.SetDefaultPrim(stage.DefinePrim('/World', 'Xform'))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(a.fps*10)
    stage.SetTimeCodesPerSecond(a.fps)
    stage.SetFramesPerSecond(a.fps)
    UsdGeom.SetStageMetersPerUnit(stage, 1.)
    UsdGeom.SetStageUpAxis(stage, 'Z')
    if a.driver in ['configured', 'physics']:
        RenderingManager.set_dt(1./a.fps)
        SimulationManager.setup_simulation(dt=1./a.fps, device='cpu')
    chamber = UsdGeom.Xform.Define(stage, '/World/Chamber')
    for axis in range(3):
        for sign in [-1, 1]:
            center = [0., 0., 0.]
            size = [20.4, 20.4, 20.4]
            center[axis], size[axis] = sign*10.1, .2
            cube = UsdGeom.Cube.Define(stage, f'/World/Chamber/w{axis}_{sign+1}')
            cube.CreateSizeAttr(1.)
            xf = UsdGeom.XformCommonAPI(cube)
            xf.SetTranslate(Gf.Vec3d(*center))
            xf.SetScale(Gf.Vec3f(*size))
    sensor = stage.DefinePrim('/World/Sensor', 'OmniLidar')
    sensor.GetReferences().AddReference('/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/config/NZ3_scan.usda')
    emitters = 100 if a.pattern == 'fixed' else 8
    for attr in sensor.GetAttributes():
        if ':emitterState:' in attr.GetName():
            value = attr.Get()
            if value is not None and hasattr(value, '__len__') and len(value) > emitters:
                attr.Set(type(value)(list(value)[:emitters]))
    overrides = {'scanType': 'ROTARY', 'instantLidar': False, 'numberOfEmitters': 8,
        'numberOfChannels': 8, 'numLines': 1, 'numRaysPerLine': [8],
        'maxReturns': 1, 'scanRateBaseHz': 10, 'patternFiringRateHz': 1000,
        'accumulateOutputs': bool(a.accumulate), 'rangeAccuracyM': 0., 'nearRangeM': .1, 'farRangeM': 100.,
        'rangeOffsetM': 0., 'outputFrameOfReference': a.reference,
        'outputMotionCompensationState': 'COMPENSATED' if a.compensated else 'NONCOMPENSATED',
        'emitterState:s001:azimuthDeg': [0.]*8,
        'emitterState:s001:elevationDeg': [-15., -10., -5., 0., 3., 5., 10., 15.],
        'emitterState:s001:fireTimeNs': [0]*8,
        'emitterState:s001:channelId': list(range(1, 9)), 'emitterState:s001:bank': [0]*8}
    if a.pattern == 'fixed':
        overrides.update({'scanType': 'SOLID_STATE', 'numberOfEmitters': emitters,
            'numberOfChannels': emitters, 'numLines': 1, 'numRaysPerLine': [emitters],
            'patternFiringRateHz': 10, 'emitterState:s001:azimuthDeg': [0.]*emitters,
            'emitterState:s001:elevationDeg': [0.]*emitters,
            'emitterState:s001:fireTimeNs': list(range(0, emitters*1000000, 1000000)),
            'emitterState:s001:channelId': list(range(1, emitters+1)),
            'emitterState:s001:bank': [0]*emitters})
    for name, value in overrides.items():
        assert sensor.GetAttribute('omni:sensor:Core:'+name).Set(value), name
    sensor.GetAttribute('omni:sensor:tickRate').Set(10.)
    sensor.GetAttribute('_replicator:rendervar:GenericModelOutput:channels').Set(['BASIC'])
    moving_prim = sensor if a.motion == 'sensor' else chamber.GetPrim()
    op = UsdGeom.Xformable(moving_prim).AddTranslateOp()
    op.Set(Gf.Vec3d(0))
    if a.motion != 'static' and a.driver != 'physics':
        # Linear X motion; integer USD time codes represent seconds * fps.
        op.Set(Gf.Vec3d(0, 0, 0), 0)
        op.Set(Gf.Vec3d(a.speed*10, 0, 0), a.fps*10)
    if a.driver == 'physics' and a.motion != 'static':
        body = UsdPhysics.RigidBodyAPI.Apply(moving_prim)
        body.CreateVelocityAttr(Gf.Vec3f(a.speed, 0, 0))
        if a.angular_speed:
            assert a.motion == 'sensor', 'Angular test rotates the sensor only'
            body.CreateAngularVelocityAttr(Gf.Vec3f(0, 0, a.angular_speed))
        mass = UsdPhysics.MassAPI.Apply(moving_prim)
        mass.CreateMassAttr(1.)
        mass.CreateDiagonalInertiaAttr(Gf.Vec3f(1, 1, 1))
        rigid_settings = PhysxSchema.PhysxRigidBodyAPI.Apply(moving_prim)
        rigid_settings.CreateDisableGravityAttr(True)
        if a.zero_damping:
            rigid_settings.CreateAngularDampingAttr(0.)
            rigid_settings.CreateLinearDampingAttr(0.)
    gmo_var = stage.DefinePrim('/Render/Vars/GenericModelOutput', 'RenderVar')
    gmo_var.CreateAttribute('sourceName', Sdf.ValueTypeNames.String).Set('GenericModelOutput')
    gmo_var.CreateAttribute('channels', Sdf.ValueTypeNames.StringArray, custom=True).Set(['BASIC'])
    product = rep.create.render_product('/World/Sensor', (1, 1), name='MotionTruth', render_vars=['GenericModelOutput'])
    annot = rep.AnnotatorRegistry.get_annotator('GenericModelOutput', device='cpu', do_array_copy=True)
    annot.attach([product.path])
    for layer in stage.GetUsedLayers():
        if layer != stage.GetRootLayer() and not layer.anonymous:
            layer.SetPermissionToEdit(False)
            layer.SetPermissionToSave(False)
    stage.GetRootLayer().Export(str(a.out/'experiment.usda'))
    tl = omni.timeline.get_timeline_interface()
    tl.set_target_framerate(a.fps)
    def frame_dict(frame):
        return {'timestampNs': int(frame.timestampNs), 'position': list(frame.posM), 'orientation': list(frame.orientation)}
    for cycle in range(a.cycles):
        seen = set()
        phase('play_'+str(cycle))
        tl.play()
        for frame in range(a.frames):
            app.update()
            sim_time = tl.get_current_time()
            gfmat = UsdGeom.Xformable(moving_prim).ComputeLocalToWorldTransform(Usd.TimeCode(sim_time*a.fps))
            mat = np.asarray(gfmat)
            quat = gfmat.ExtractRotationQuat()
            r['updates'].append({'cycle': cycle, 'frame': frame, 'time': sim_time,
                'physics_time': float(SimulationManager.get_simulation_time()), 'moving_position': mat[3, :3].tolist(),
                'moving_orientation_xyzw': list(quat.GetImaginary()) + [quat.GetReal()]})
            raw = annot.get_data()
            if isinstance(raw, dict):
                raw = raw.get('data')
            if raw is None or not len(raw):
                continue
            g = parse_generic_model_output_data(raw)
            if not g.numElements or (a.accumulate and not g.scanComplete):
                continue
            stamp = int(g.timestampNs)
            key = stamp if a.accumulate else (stamp, int(g.frameId))
            if key in seen:
                continue
            if stamp*1e-9 > sim_time+.2:
                r['stale'].append({'cycle': cycle, 'frame': frame, 'timestampNs': stamp, 'timeline': sim_time})
                continue
            seen.add(key)
            xyz = np.column_stack((g.x, g.y, g.z)).copy()
            arrays = {'xyz': xyz, 'timeOffsetNs': np.asarray(g.timeOffsetNs).copy(),
                'emitterId': np.asarray(g.emitterId).copy(), 'flags': np.asarray(g.flags).copy()}
            filename = f'scan_{cycle}_{stamp:012d}' + (f'_{int(g.frameId)}' if not a.accumulate else '') + '.npz'
            np.savez_compressed(a.out/filename, **arrays)
            row = {'cycle': cycle, 'frame': frame, 'timeline': sim_time, 'timestampNs': stamp,
                'frameId': int(g.frameId), 'count': int(g.numElements), 'scanComplete': int(g.scanComplete),
                'frameOfReference': str(g.frameOfReference), 'motionCompensationState': str(g.motionCompensationState),
                'frameStart': frame_dict(g.frameStart), 'frameEnd': frame_dict(g.frameEnd),
                'modelToAppTransform': np.asarray(g.modelToAppTransform).tolist(), 'file': filename}
            r['samples'].append(row)
        phase('stop_'+str(cycle))
        tl.stop()
        for _ in range(5):
            app.update()
    annot.detach([product.path])
    product.destroy()
    r['status'] = 'collected' if r['samples'] else 'no_data'
    phase('completed')
except BaseException:
    r['status'] = 'python_error'
    r['error'] = traceback.format_exc()
    print(r['error'], flush=True)
finally:
    (a.out/'result.json').write_text(json.dumps(r, indent=2))
    app.close(wait_for_replicator=False)
