"""Inspect composed camera transforms without starting Kit or writing USD."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

assets = Path('/root/gpufree-data/IsaacSim_Asset')
project = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
scene = assets / 'combine_stage/combine_scene_15_surround_fisheye.usda'
out = {'files': {}, 'camera_world': [], 'snapshot': {}, 'processes': []}
for p in [assets / 'combine_stage/combine_scene_13_3dgs_contract.usda',
          assets / 'excavator_module_set/Excavator_3DGS_Contract/Excavator_3DGS_Contract.usda']:
    raw = p.read_bytes()
    out['files'][str(p)] = {'sha256': hashlib.sha256(raw).hexdigest(),
                          'text': raw.decode('utf-8') if len(raw) < 100000 else None}
snapshot = project / 'reports/surround_fisheye/recordings/camera_snapshots/20260921_181525_044027_bffdae'
if snapshot.exists():
    for p in sorted(snapshot.rglob('*')):
        if not p.is_file():
            continue
        if p.suffix in ['.json', '.jsonl', '.png']:
            raw = p.read_bytes()
            out['snapshot'][str(p.relative_to(snapshot))] = {
                'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'text': raw.decode('utf-8') if p.suffix in ['.json', '.jsonl'] and len(raw) < 40000 else None}
libs = sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))
try:
    sys.path.insert(0, str(libs[-1]))
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(scene), load=Usd.Stage.LoadNone)
    stage.Load('/World/Excavator', Usd.LoadWithoutDescendants)
    cache = UsdGeom.XformCache()
    for camera in ['Front', 'Rear', 'Left', 'Right']:
        path = '/World/Excavator/swing_link/Fisheye' + camera
        prim = stage.GetPrimAtPath(path)
        m = cache.GetLocalToWorldTransform(prim)
        row = {'id': camera.lower(), 'path': path,
               'usd_to_world': [[float(m[i][j]) for j in range(4)] for i in range(4)]}
        row['lens'] = {a.GetName(): str(a.Get()) for a in prim.GetAttributes()
                       if a.GetName().startswith('omni:lensdistortion')}
        out['camera_world'].append(row)
    root = cache.GetLocalToWorldTransform(stage.GetPrimAtPath('/World/Excavator'))
    out['excavator_to_world'] = [[float(root[i][j]) for j in range(4)] for i in range(4)]
    out['used_layer_identifiers'] = [p.identifier for p in stage.GetUsedLayers()]
except Exception as e:
    out['usd_error'] = type(e).__name__ + ': ' + str(e)
    # USD's existing shared libraries need a process-local loader path.
    native = list(libs[-1].rglob('libusd_tf.so'))
    if native:
        env = dict(os.environ)
        env['LD_LIBRARY_PATH'] = str(native[0].parent) + ':/root/isaacsim/kit/lib'
        child = '''import json,sys
sys.path.insert(0,sys.argv[1])
from pxr import Usd,UsdGeom
s=Usd.Stage.Open(sys.argv[2],load=Usd.Stage.LoadNone)
s.Load('/World/Excavator',Usd.LoadWithoutDescendants)
c=UsdGeom.XformCache()
out=[]
for n in ['Front','Rear','Left','Right']:
 p=s.GetPrimAtPath('/World/Excavator/swing_link/Fisheye'+n)
 m=c.GetLocalToWorldTransform(p)
 out.append({'id':n.lower(),'usd_to_world':[[float(m[i][j]) for j in range(4)] for i in range(4)]})
print(json.dumps(out))
'''
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', child, str(libs[-1]), str(scene)],
                                env=env, capture_output=True, text=True, timeout=15)
        out['usd_retry_exit_code'] = result.returncode
        if result.returncode == 0:
            out['camera_world'] = json.loads(result.stdout)
        else:
            out['usd_retry_error'] = result.stderr[-2000:]
recording = project / 'reports/surround_fisheye/recordings/20260921_181528_054957_cdb6ab'
out['recording_first_images'] = {}
for camera in ['front', 'rear', 'left', 'right']:
    directory = recording / 'cameras' / camera / 'images'
    images = sorted(directory.glob('*.png'))
    if images:
        out['recording_first_images'][camera] = {'path': str(images[0]),
            'sha256': hashlib.sha256(images[0].read_bytes()).hexdigest(), 'count': len(images)}
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        name = (p / 'comm').read_text().strip()
        if name.lower() in ['kit', 'isaac-sim', 'isaacsim']:
            out['processes'].append({'pid': int(p.name), 'name': name})
    except OSError:
        pass
print(json.dumps(out, ensure_ascii=False))
