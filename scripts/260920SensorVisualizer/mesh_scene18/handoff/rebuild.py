"""Rebuild the exact five-part mesh asset from frozen mesh input and rig blueprint.

Requires the existing OpenUSD + NumPy environment, no Isaac app or 3DGS input.
Writes only to a NEW directory. Compare against reference/ after rebuilding.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
from pxr import Sdf, Usd, UsdGeom, UsdShade, Vt

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source', type=Path, default=HERE/'inputs/waji_mesh_corrected.usdc')
    args = parser.parse_args()
    cfg = json.loads((HERE/'reconstruction.json').read_text(encoding='utf-8'))
    template = HERE/'inputs/rig_template.usda'
    if sha(args.source) != cfg['source_sha256']:
        raise ValueError('Input mesh differs from the frozen canonical source.')
    if sha(template) != cfg['rig_template_sha256']:
        raise ValueError('Rig blueprint differs from the frozen version.')
    if args.output.exists():
        raise FileExistsError('Choose a NEW output directory; existing assets are never overwritten.')
    source = Usd.Stage.Open(str(args.source))
    layer = source.Flatten(addSourceFileComment=False)
    (args.output/'geometry').mkdir(parents=True)
    shutil.copyfile(template, args.output/'Excavator_Mesh_Contract.usda')
    for frame, info in cfg['parts'].items():
        prim = source.GetPrimAtPath(info['source_prim'])
        if not prim.IsA(UsdGeom.Mesh):
            raise ValueError('Missing mesh: '+info['source_prim'])
        points = np.asarray(prim.GetAttribute('points').Get())
        colors = np.asarray(prim.GetAttribute('primvars:Col').Get())
        if len(points) != info['vertices'] or colors.shape != (len(points),4):
            raise ValueError('Unexpected geometry or color array shape.')
        if not np.isfinite(colors).all() or not np.array_equal(colors[:,3],np.ones(len(points))):
            raise ValueError('Canonical source must have finite, fully opaque vertex colors.')
        geo = Usd.Stage.CreateNew(str(args.output/'geometry'/f'{frame}.usdc'))
        root = UsdGeom.Xform.Define(geo,'/Geometry').GetPrim()
        geo.SetDefaultPrim(root)
        UsdGeom.SetStageMetersPerUnit(geo,1)
        UsdGeom.SetStageUpAxis(geo,UsdGeom.Tokens.z)
        if not Sdf.CopySpec(layer,info['source_prim'],geo.GetRootLayer(),'/Geometry/Mesh'):
            raise RuntimeError('Unable to copy mesh spec.')
        mesh = geo.GetPrimAtPath('/Geometry/Mesh')
        color = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('displayColor',Sdf.ValueTypeNames.Color3fArray,UsdGeom.Tokens.vertex)
        color.Set(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(colors[:,:3],dtype=np.float32)))
        material = UsdShade.Material.Define(geo,'/Geometry/Looks/VertexColor')
        surface = UsdShade.Shader.Define(geo,'/Geometry/Looks/VertexColor/Surface')
        surface.CreateIdAttr('UsdPreviewSurface')
        surface.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.8)
        surface.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(0)
        reader = UsdShade.Shader.Define(geo,'/Geometry/Looks/VertexColor/Color')
        reader.CreateIdAttr('UsdPrimvarReader_float3')
        reader.CreateInput('varname',Sdf.ValueTypeNames.Token).Set('displayColor')
        surface.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.CreateOutput('result',Sdf.ValueTypeNames.Float3))
        material.CreateSurfaceOutput().ConnectToSource(surface.CreateOutput('surface',Sdf.ValueTypeNames.Token))
        UsdShade.MaterialBindingAPI.Apply(mesh).Bind(material)
        geo.GetRootLayer().Save()
    rebuilt = Usd.Stage.Open(str(args.output/'Excavator_Mesh_Contract.usda'))
    reference = Usd.Stage.Open(str(HERE/'reference/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda'))
    result = {'input_sha256':sha(args.source),'runtime':{'usd':list(Usd.GetVersion()),'numpy':np.__version__},
        'composed_usda_identical':rebuilt.Flatten(addSourceFileComment=False).ExportToString()==reference.Flatten(addSourceFileComment=False).ExportToString(),
        'files':{},'source_array_equality':{}}
    for path in sorted(args.output.rglob('*')):
        if not path.is_file(): continue
        rel = path.relative_to(args.output)
        ref = HERE/'reference/Excavator_Mesh_Contract'/rel
        result['files'][rel.as_posix()] = {'sha256':sha(path),'reference_sha256':sha(ref),'bytes_equal':path.read_bytes()==ref.read_bytes()}
    for frame,info in cfg['parts'].items():
        src = source.GetPrimAtPath(info['source_prim'])
        dst = rebuilt.GetPrimAtPath(f'/Excavator/{frame}/Visuals/MeshAlignment/Geometry/Mesh')
        result['source_array_equality'][frame] = {name:np.array_equal(np.asarray(src.GetAttribute(name).Get()),np.asarray(dst.GetAttribute(name).Get()))
            for name in info['preserved_numeric_attributes']}
    result['all_six_usd_files_byte_identical'] = all(x['bytes_equal'] for x in result['files'].values())
    result['passed'] = result['composed_usda_identical'] and all(all(x.values()) for x in result['source_array_equality'].values())
    (args.output/'rebuild_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit('Reconstruction verification FAILED; output retained for diagnosis.')

if __name__ == '__main__': main()
