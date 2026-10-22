"""Independent RTX validation using USD references and native GMO, no production stage edits."""
import argparse
import json
import time
import traceback
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--asset', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--smoke', action='store_true')
parser.add_argument('--inspect-source', action='store_true')
parser.add_argument('--sensitivity-control', action='store_true')
parser.add_argument('--zero-noise', action='store_true')
args, _ = parser.parse_known_args()
args.output.mkdir(parents=True, exist_ok=True)
# An interrupted rerun must never leave a previous success as its result.
(args.output/'validation.json').write_text(json.dumps(dict(passed=False, status='starting'))+'\n', encoding='utf-8')

from isaacsim import SimulationApp
app = SimulationApp(dict(headless=True, multi_gpu=False, fast_shutdown=True,
    renderer='RaytracedLighting', width=640, height=480,
    extra_args=['--/renderer/raytracingMotion/enabled=false',
                '--/rtx/hydra/supportMultiTickRate=false',
                '--/rtx/rendering/perSensorTickTlas=false',
                '--/persistent/app/usd/muteUsdDiagnostics=false']))
import numpy as np
import omni.usd
import omni.timeline
import omni.replicator.core as rep
from pxr import Usd, UsdGeom, Gf, Sdf
from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data

TOTAL = 96 * 892
P = 'omni:sensor:Core:'
timeline = omni.timeline.get_timeline_interface()
result = dict(passed=False, asset=str(args.asset), samples=TOTAL, phases={})
runtimes = []


def cube(stage, path, center, size):
    obj = UsdGeom.Cube.Define(stage, path)
    obj.CreateSizeAttr(1)
    xf = UsdGeom.XformCommonAPI(obj)
    xf.SetTranslate(Gf.Vec3d(*center)); xf.SetScale(Gf.Vec3f(*size))
    return np.asarray(center)-np.asarray(size)/2, np.asarray(center)+np.asarray(size)/2


def intersection(origin, directions, lower, upper):
    lo, hi = lower-origin, upper-origin
    parallel = np.abs(directions) < 1e-12
    safe = np.where(parallel, 1, directions)
    t1, t2 = lo/safe, hi/safe
    near = np.where(parallel, -np.inf, np.minimum(t1,t2)).max(axis=1)
    far = np.where(parallel, np.inf, np.maximum(t1,t2)).min(axis=1)
    hit = (~(parallel & ((lo > 0) | (hi < 0))).any(axis=1)) & (far >= np.maximum(near, 0))
    return np.where(hit, np.where(near > 0, near, far), np.inf)


def attach(stage, path, translation, rotation):
    root = stage.DefinePrim(path, 'Xform')
    root.GetReferences().AddReference(str(args.asset))
    xf = UsdGeom.XformCommonAPI(root)
    xf.SetTranslate(Gf.Vec3d(*translation)); xf.SetRotate(Gf.Vec3f(*rotation))
    sensor = stage.GetPrimAtPath(path+'/sensor')
    get = lambda name: sensor.GetAttribute(P+name).Get()
    assert sensor.GetTypeName() == 'OmniLidar'
    if args.zero_noise:
        sensor.GetAttribute(P+'rangeAccuracyM').Set(0)
    assert get('scanType') == 'SOLID_STATE' and get('instantLidar')
    assert get('rangeOffsetM') == 0 and get('numberOfEmitters') == TOTAL
    assert list(get('numRaysPerLine')) == [892]*96
    assert get('numberOfChannels') == TOTAL
    assert not np.any(get('emitterState:s001:fireTimeNs'))
    assert list(get('emitterState:s001:channelId')) == list(range(1, TOTAL+1))
    root_m = UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    sensor_m = UsdGeom.Xformable(sensor).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    assert np.allclose(np.array(root_m), np.array(sensor_m), atol=1e-10)
    az = -np.radians(np.asarray(get('emitterState:s001:azimuthDeg'), dtype=float))
    el = np.radians(np.asarray(get('emitterState:s001:elevationDeg'), dtype=float))
    directions = np.column_stack((np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)))
    assert directions.shape == (TOTAL, 3) and directions[:,2].min() >= -1e-7
    product = rep.create.render_product(str(sensor.GetPath()), (1,1), name='AiryTest'+path.rsplit('/',1)[-1],
                                        render_vars=['GenericModelOutput'])
    annot = rep.AnnotatorRegistry.get_annotator('GenericModelOutput', device='cpu', do_array_copy=True)
    annot.attach([product.path])
    rt = dict(path=path, sensor=sensor, product=product, annot=annot, dirs=directions)
    runtimes.append(rt)
    return rt


def frame(rt):
    raw = rt['annot'].get_data()
    if isinstance(raw, dict): raw = raw.get('data')
    if raw is None or not len(raw): return None
    g = parse_generic_model_output_data(raw)
    if not g.numElements or not g.scanComplete:
        if rt.get('empty_debug',0)<2:
            print('AIRY_BUFFER',rt['path'],int(g.numElements),int(g.scanComplete),flush=True)
            rt['empty_debug']=rt.get('empty_debug',0)+1
        return None
    xyz = np.column_stack((g.x, g.y, g.z)).copy()
    ids = np.asarray(g.emitterId, dtype=np.int64).copy()
    channel = np.asarray(g.channelId, dtype=np.int64).copy()
    keep = np.isfinite(xyz).all(axis=1) & (np.linalg.norm(xyz,axis=1)>0)
    xyz, ids, channel = xyz[keep], ids[keep], channel[keep]
    assert len(ids) and ids.min() >= 0 and ids.max() < TOTAL, 'Emitter IDs out of range'
    # Detect uint16 truncation: this profile intentionally exceeds 65,535 channels.
    assert np.array_equal(channel, ids), 'Channel/emitter IDs diverge'
    return dict(xyz=xyz, ids=ids, frame_id=int(g.frameId), scan_complete=bool(g.scanComplete))


def check_frame(stage, rt, data, boxes, tolerance):
    matrix = np.array(UsdGeom.Xformable(rt['sensor']).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    directions = rt['dirs'] @ matrix[:3,:3]
    expected = np.min([intersection(matrix[3,:3], directions, lo, hi) for lo,hi in boxes], axis=0)
    distances = np.linalg.norm(data['xyz'], axis=1)
    observed = data['xyz']/distances[:,None]
    rays = rt['dirs'][data['ids']]
    angle = np.degrees(np.arctan2(np.linalg.norm(np.cross(observed, rays),axis=1), (observed*rays).sum(axis=1)))
    error = np.abs(distances-expected[data['ids']])
    if error.max()>=tolerance:
        worst=np.argsort(error)[-5:]
        print('AIRY_RANGE_ERROR',json.dumps(dict(points=len(distances),unique=int(len(np.unique(data['ids']))),
              ids=data['ids'][worst].tolist(),actual=distances[worst].tolist(),expected=expected[data['ids'][worst]].tolist())),flush=True)
        np.savez_compressed(args.output/'unexpected_frame.npz',**data,expected=expected)
    assert angle.max() < .006, f'Wrong directions: {angle.max()}'
    assert error.max() < tolerance, f'Wrong ranges: {error.max()}'
    return dict(points=len(distances), unique_emitters=int(len(np.unique(data['ids']))),
                max_emitter_id=int(data['ids'].max()), frame_id=data['frame_id'],
                scan_complete=data['scan_complete'], max_angle_error_deg=float(angle.max()),
                max_range_error_m=float(error.max()), world_origin=matrix[3,:3].tolist())


def sample(stage, boxes, label, tolerance=.15, warmup=15, require_full=True):
    for _ in range(warmup): app.update()
    reports = {}; previous = {}; fresh_counts = {rt['path']:0 for rt in runtimes}
    coverage = {rt['path']:np.zeros(TOTAL,dtype=bool) for rt in runtimes}
    counts = {rt['path']:[] for rt in runtimes}
    started = time.monotonic()
    for _ in range(100):
        app.update()
        for rt in runtimes:
            data = frame(rt)
            if data is None: continue
            key=rt['path']
            if previous.get(key) == data['frame_id']: continue
            previous[key] = data['frame_id']; fresh_counts[key] += 1
            report = check_frame(stage, rt, data, boxes, tolerance)
            if fresh_counts[key] <= 3:
                print('AIRY_SAMPLE',label,key,json.dumps(report),flush=True)
            coverage[key][data['ids']]=True
            counts[key].append(report['unique_emitters'])
            # Complete scans can lose individual echoes under the inherited
            # physical return filter. Validate single-frame density separately
            # from all-emitter coverage across a few stationary snapshots.
            if require_full:
                assert report['unique_emitters'] >= TOTAL*.999, 'Unexpectedly sparse full scan'
            reports[key]=report
            if fresh_counts[key] == 1:
                np.savez_compressed(args.output/(label+'_'+key.rsplit('/',1)[-1]+'.npz'), **data)
        if (len(reports)==len(runtimes) and min(fresh_counts.values())>=3
                and (not require_full or all(v.all() for v in coverage.values()))): break
    assert len(reports)==len(runtimes), f'Missing complete per-frame output: {reports}; fresh={fresh_counts}'
    assert min(fresh_counts.values())>=3
    if require_full: assert all(v.all() for v in coverage.values()), 'Some directions never returned'
    result['phases'][label]=dict(sensors=reports,fresh_frames=fresh_counts,
        coverage={k:dict(union_emitters=int(v.sum()),per_frame_unique_min=min(counts[k]),
                        per_frame_unique_max=max(counts[k])) for k,v in coverage.items()},
        wall_seconds=time.monotonic()-started)
    (args.output/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('AIRY_PHASE',label,json.dumps(result['phases'][label]),flush=True)


try:
    omni.usd.get_context().new_stage()
    stage = omni.usd.get_context().get_stage()
    stage.SetDefaultPrim(stage.DefinePrim('/World','Xform'))
    UsdGeom.SetStageMetersPerUnit(stage,1); UsdGeom.SetStageUpAxis(stage,'Z')
    stage.SetTimeCodesPerSecond(60); stage.SetEndTimeCode(1000)
    boxes=[]
    for axis in range(3):
        for sign in (-1,1):
            center=[0.,0.,0.]; center[axis]=sign*2.1
            size=[4.4]*3; size[axis]=.2
            boxes.append(cube(stage,f'/World/room/wall_{axis}_{sign+1}',center,size))
    a=attach(stage,'/World/MyAiry_A',(0,0,0),(0,0,0))
    if not args.smoke: b=attach(stage,'/World/MyAiry_B',(.2,-.15,.1),(180,0,27))
    if args.sensitivity_control:
        for rt in runtimes:
            rt['sensor'].GetAttribute(P+'minReflectance').Set(.000001)
    if args.inspect_source:
        source=Usd.Stage.Open('/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/Rotator360_90/MyOS0.usda')
        prim=source.GetPrimAtPath('/OS0/sensor')
        source_attrs={at.GetName():str(at.Get()) for at in prim.GetAttributes()
                      if at.GetName().startswith('omni:sensor:') and 'emitterState' not in at.GetName()}
        result['source_attributes']=source_attrs
        print('AIRY_SOURCE',json.dumps(source_attrs),flush=True)
        snapshot={at.GetName():dict(type=str(at.GetTypeName()),value=str(at.Get())) for at in prim.GetAttributes()
                  if at.GetName().startswith(P) and 'emitterState' not in at.GetName()}
        (args.output/'source_attributes.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
        difference={name:dict(source=val, candidate=str(a['sensor'].GetAttribute(name).Get()))
                    for name,val in source_attrs.items()
                    if str(a['sensor'].GetAttribute(name).Get())!=val}
        print('AIRY_DIFF',json.dumps(difference),flush=True)
        raise RuntimeError('Inspection-only run: source attributes exported')
    timeline.play()
    tolerance=.002 if args.zero_noise else .15
    sample(stage,boxes,'zero_noise' if args.zero_noise else 'authored_asset',warmup=40,tolerance=tolerance)
    if not args.smoke:
        xf=UsdGeom.XformCommonAPI(stage.GetPrimAtPath(a['path']))
        xf.SetTranslate(Gf.Vec3d(.4,-.3,.2)); xf.SetRotate(Gf.Vec3f(12,15,-31))
        sample(stage,boxes,'moved',tolerance=tolerance)
        timeline.pause()
        xf.SetTranslate(Gf.Vec3d(0,0,0)); xf.SetRotate(Gf.Vec3f(0,0,0))
        blocker=cube(stage,'/World/near_blocker',(.06,0,.3),(.02,.3,.8))
        timeline.play()
        sample(stage,boxes+[blocker],'near_occluder',tolerance=tolerance,require_full=False)
        matrix=np.array(UsdGeom.Xformable(a['sensor']).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        near=intersection(matrix[3,:3],a['dirs']@matrix[:3,:3],*blocker)
        blocked=near < .1
        assert blocked.sum()>100
        f=frame(a)
        leaks=int((blocked[f['ids']] & (np.linalg.norm(f['xyz'],axis=1)>.2)).sum())
        assert leaks==0, f'Near object failed to occlude {leaks} returns'
        result['near_occluder']=dict(rays_blocked_inside_minimum_range=int(blocked.sum()),far_return_leaks=leaks)
        stage.RemovePrim('/World/near_blocker')
        sample(stage,boxes,'pause_resume',tolerance=tolerance)
        timeline.stop()
        for _ in range(6):app.update()
        timeline.play()
        sample(stage,boxes,'stop_play',tolerance=tolerance)
    result['passed']=True
except Exception:
    result['error']=traceback.format_exc()
    print(result['error'],flush=True)
finally:
    timeline.stop()
    for rt in runtimes:
        rt['annot'].detach([rt['product'].path]); rt['product'].destroy()
    (args.output/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('AIRY_RESULT',json.dumps(result),flush=True)
    app.close()
if not result['passed']: raise SystemExit(1)
