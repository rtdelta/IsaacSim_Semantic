"""Read and sample paired GS/Mesh geometry without attaching the source to a renderer."""
import argparse
import json
from pathlib import Path
import traceback
p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
a, _ = p.parse_known_args()
a.out.mkdir(parents=True, exist_ok=True)
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'fast_shutdown': True, 'limit_cpu_threads': 8,
    'extra_args': ['--/app/settings/loadUserConfig=false', '--/app/settings/persistent=false',
                   '--/renderer/raytracingMotion/enabled=false']})
try:
    import numpy as np
    from pxr import Usd, UsdGeom
    source = '/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_11_origin03.usda'
    stage = Usd.Stage.CreateInMemory()
    stage.GetRootLayer().subLayerPaths = [source]
    for layer in stage.GetUsedLayers():
        if layer != stage.GetRootLayer() and not layer.anonymous:
            layer.SetPermissionToEdit(False)
            layer.SetPermissionToSave(False)
    root = stage.GetPrimAtPath('/Excavator_Fangshan_05')
    root.GetVariantSets().GetVariantSet('visualization').SetVariantSelection('source_mesh')
    rng = np.random.default_rng(20260917)
    metadata = {'source': source, 'meters_per_unit': UsdGeom.GetStageMetersPerUnit(stage),
                'up_axis': str(UsdGeom.GetStageUpAxis(stage)), 'gaussians': [], 'meshes': []}
    def matrix(prim):
        return np.asarray(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=float)
    def world(points, mat):
        return points @ mat[:3, :3] + mat[3, :3]
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if not path.startswith('/Excavator_Fangshan_05/'):
            continue
        if 'ParticleField' in prim.GetTypeName():
            positions = prim.GetAttribute('positions').Get()
            if positions is None:
                positions = prim.GetAttribute('positionsh').Get()
            points = np.asarray(positions, dtype=float)
            alpha = prim.GetAttribute('opacities').Get()
            if alpha is None:
                alpha = prim.GetAttribute('opacitiesh').Get()
            alpha = np.asarray(alpha, dtype=float)
            if alpha.size != len(points):
                raise RuntimeError('Opacity length mismatch: ' + path)
            idx = rng.choice(len(points), size=min(15000, len(points)), replace=False)
            mat = matrix(prim)
            wp = world(points[idx], mat)
            name = 'gs_' + str(len(metadata['gaussians'])) + '.npz'
            np.savez_compressed(a.out/name, positions=wp, opacities=alpha[idx], transform=mat)
            metadata['gaussians'].append({'path': path, 'name': prim.GetName(), 'file': name,
                'total': len(points), 'sampled': len(idx), 'opacity_range': [float(alpha.min()), float(alpha.max())],
                'world_bounds': [world(points, mat).min(axis=0).tolist(), world(points, mat).max(axis=0).tolist()]})
        elif prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            points = np.asarray(mesh.GetPointsAttr().Get(), dtype=float)
            counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=int)
            indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=int)
            visible = UsdGeom.Imageable(prim).ComputeVisibility() == 'inherited'
            group = 'source_mesh' if '/Visuals/Mesh/' in path else 'reference_or_other'
            row = {'path': path, 'name': prim.GetName(), 'visible': visible,
                   'purpose': str(UsdGeom.Imageable(prim).ComputePurpose()),
                   'group': group, 'vertices': len(points), 'polygons': len(counts),
                   'subdivision': str(mesh.GetSubdivisionSchemeAttr().Get())}
            if group == 'source_mesh':
                mat = matrix(prim)
                wp = world(points, mat)
                faces, offset = [], 0
                for count in counts:
                    poly = indices[offset:offset+count]
                    for j in range(1, count-1):
                        faces.append([int(poly[0]), int(poly[j]), int(poly[j+1])])
                    offset += count
                row['file'] = 'mesh_' + str(len(metadata['meshes'])) + '.npz'
                row['nontriangle_faces'] = int((counts != 3).sum())
                row['world_bounds'] = [wp.min(axis=0).tolist(), wp.max(axis=0).tolist()]
                np.savez_compressed(a.out/row['file'], vertices=wp, faces=np.asarray(faces, dtype=np.int32), transform=mat)
            metadata['meshes'].append(row)
    assert len(metadata['gaussians']) == 15
    (a.out/'geometry.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps({'gs': len(metadata['gaussians']), 'meshes': metadata['meshes']}, indent=2), flush=True)
except BaseException:
    (a.out/'error.txt').write_text(traceback.format_exc())
    raise
finally:
    app.close(wait_for_replicator=False)
