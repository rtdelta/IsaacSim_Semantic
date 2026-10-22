"""Read-only USD inspection; run with Isaac USD libraries, without starting Kit."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
import numpy as np
from pxr import Usd, UsdGeom

root = Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02')
result = {'sources': {}, 'assets': {}, 'sessions': []}
for part, source in [('track', 'track'), ('cab', 'operator_cab'), ('boom', 'boom'), ('arm', 'small_arm'), ('bucket_without_teeth', 'bucket_without_teeth')]:
    stage = Usd.Stage.Open(str(root / '3dgs_usd' / (source + '.usd')))
    prim = stage.GetDefaultPrim()
    xyz = np.asarray(prim.GetAttribute('positions').Get(), dtype=np.float64)
    indices = np.linspace(0, len(xyz) - 1, 512, dtype=int)
    result['sources'][part] = {
        'path': str(root / '3dgs_usd' / (source + '.usd')),
        'count': len(xyz), 'indices': indices.tolist(), 'positions': xyz[indices].tolist(),
        'up_axis': str(UsdGeom.GetStageUpAxis(stage)),
        'bounds': [xyz.min(0).tolist(), xyz.max(0).tolist()],
    }
for name in ['Excavator_Fangshan_05.usda', 'Excavator_Fangshan_05_origin03.usda']:
    path = root / name
    stage = Usd.Stage.Open(str(path), load=Usd.Stage.LoadNone)
    data = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'parts': {}}
    for part in ['track', 'cab', 'boom', 'arm', 'bucket']:
        body = stage.GetPrimAtPath('/Excavator/' + part + '_prim')
        gs = stage.GetPrimAtPath(str(body.GetPath()) + '/Visuals/GS')
        data['parts'][part] = {
            'body_local_column_matrix': np.asarray(UsdGeom.Xformable(body).GetLocalTransformation()).T.tolist(),
            'gs_local_column_matrix': np.asarray(UsdGeom.Xformable(gs).GetLocalTransformation()).T.tolist(),
        }
    result['assets'][name] = data
outroot = Path('/root/gpufree-data/semantic/output/lidar_visualizer')
for p in sorted(outroot.glob('*/session.json')):
    if p.parent.name.startswith('2026091'):
        d = json.loads(p.read_text())
        result['sessions'].append({'path': str(p), 'stage': d.get('stage'), 'stage_path': d.get('stage_path'), 'created_utc': d.get('created_utc')})
print(json.dumps(result))
