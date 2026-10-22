"""Create the mesh-only contract asset and scene18; all existing assets stay untouched."""
import contextlib,hashlib,io,json,runpy,shutil,time
from pathlib import Path
import numpy as np
from pxr import Gf,Sdf,Usd,UsdGeom,UsdShade,Vt

PROJECT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
WORK=PROJECT/'mesh_scene18'
ROOT=Path('/root/gpufree-data/IsaacSim_Asset')
SCENE=ROOT/'combine_stage/combine_scene_17_terrain_fisheye.usda'
TARGET=ROOT/'combine_stage/combine_scene_18_terrain_fisheye_mesh.usda'
OLD=ROOT/'excavator_module_set/Excavator_3DGS_Contract/Excavator_3DGS_Contract.usda'
SOURCE=ROOT/'excavator_module_set/Sim_Fangshan_02/waji_mesh_corrected.usdc'
BUNDLE=ROOT/'excavator_module_set/Excavator_Mesh_Contract'
ASSET=BUNDLE/'Excavator_Mesh_Contract.usda'
PARTS={'track_link':'track','swing_link':'operator_cab','boom_link':'boom','arm_link':'small_arm','bucket_link':'bucket_only_full_teeth'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

for p in (BUNDLE,TARGET):
    assert p.resolve().is_relative_to(ROOT.resolve())
    if p.exists():raise FileExistsError('Refusing to overwrite existing output: '+str(p))
baseline=Usd.Stage.Open(str(SCENE))
source_files={l.realPath.split('[',1)[0] for l in baseline.GetUsedLayers() if l.realPath}
source_hashes={p:sha(p) for p in sorted(source_files)}
source_hashes[str(SOURCE)]=sha(SOURCE)
with contextlib.redirect_stdout(io.StringIO()):
    evidence=runpy.run_path(str(WORK/'analyze_alignment.py'))['report']
assert max(r['max'] for r in evidence['gaussian_checks'].values())<1e-6
assert evidence['mesh_global_correspondence']['rounded_1mm_vertex_match_fraction']>.999
assert evidence['mesh_global_correspondence']['sampled_128_nearest_vertex_max']<1e-6
corr=Gf.Matrix4d(*np.asarray(evidence['corrected_to_raw']).ravel().tolist())
stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
backup=WORK/'backups'/stamp;backup.mkdir(parents=True,exist_ok=False)
shutil.copy2(SCENE,backup/SCENE.name);shutil.copy2(OLD,backup/OLD.name)
dump(backup/'source_hashes.json',source_hashes)
(BUNDLE/'geometry').mkdir(parents=True,exist_ok=False)
dump(WORK/'alignment.json',evidence)
source=Usd.Stage.Open(str(SOURCE))
source_layer=source.Flatten()
manifest={'version':'mesh_contract_scene18_v1','created_utc':stamp,'source_scene':str(SCENE),'source_scene_sha256':sha(SCENE),'source_mesh':str(SOURCE),'source_mesh_sha256':sha(SOURCE),'source_contract':str(OLD),'source_contract_sha256':sha(OLD),'coordinate_evidence':evidence,'parts':{},'bucket_policy':'Complete original bucket_only_full_teeth_mesh; no clipping or tooth removal','geometry_policy':'Original mesh points/normals/topology retained; corrected-to-raw transform under existing Visuals; existing 2.4 scale remains only once','material_policy':'Original linear RGBA vertex colors preserved as Col and mapped to displayColor; opaque UsdPreviewSurface roughness 0.8','backup_directory':str(backup)}

Sdf.Layer.FindOrOpen(str(OLD)).Export(str(ASSET))
asset=Usd.Stage.Open(str(ASSET),load=Usd.Stage.LoadNone)
for frame,part in PARTS.items():
    pp=f'/root/{part}_mesh/{part}_mesh'
    source_prim=source.GetPrimAtPath(pp)
    assert source_prim.IsA(UsdGeom.Mesh)
    geo_file=BUNDLE/'geometry'/f'{frame}.usdc'
    geo=Usd.Stage.CreateNew(str(geo_file))
    root=UsdGeom.Xform.Define(geo,'/Geometry').GetPrim();geo.SetDefaultPrim(root)
    UsdGeom.SetStageMetersPerUnit(geo,1);UsdGeom.SetStageUpAxis(geo,UsdGeom.Tokens.z)
    assert Sdf.CopySpec(source_layer,pp,geo.GetRootLayer(),'/Geometry/Mesh')
    mesh=geo.GetPrimAtPath('/Geometry/Mesh')
    colors=np.asarray(mesh.GetAttribute('primvars:Col').Get())
    points=np.asarray(mesh.GetAttribute('points').Get())
    assert len(colors)==len(points) and colors.shape[1]==4 and np.isfinite(colors).all()
    assert np.max(np.abs(colors[:,3]-1))<1e-6
    pv=UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('displayColor',Sdf.ValueTypeNames.Color3fArray,UsdGeom.Tokens.vertex)
    pv.Set(Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(colors[:,:3],dtype=np.float32)))
    material=UsdShade.Material.Define(geo,'/Geometry/Looks/VertexColor')
    shader=UsdShade.Shader.Define(geo,'/Geometry/Looks/VertexColor/Surface');shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.8)
    shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(0)
    reader=UsdShade.Shader.Define(geo,'/Geometry/Looks/VertexColor/Color');reader.CreateIdAttr('UsdPrimvarReader_float3')
    reader.CreateInput('varname',Sdf.ValueTypeNames.Token).Set('displayColor')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.CreateOutput('result',Sdf.ValueTypeNames.Float3))
    material.CreateSurfaceOutput().ConnectToSource(shader.CreateOutput('surface',Sdf.ValueTypeNames.Token))
    UsdShade.MaterialBindingAPI.Apply(mesh).Bind(material)
    geo.GetRootLayer().Save()
    visual=f'/Excavator/{frame}/Visuals'
    assert asset.RemovePrim(visual+'/Splat')
    alignment=UsdGeom.Xform.Define(asset,visual+'/MeshAlignment');alignment.AddTransformOp().Set(corr)
    geometry=asset.DefinePrim(visual+'/MeshAlignment/Geometry')
    geometry.GetPayloads().AddPayload('./geometry/'+geo_file.name)
    manifest['parts'][frame]={'source_prim':pp,'geometry_file':str(geo_file),'target_geometry_path':visual+'/MeshAlignment/Geometry/Mesh','vertices':len(points),'faces':len(mesh.GetAttribute('faceVertexCounts').Get()),'corrected_to_raw_row_matrix':evidence['corrected_to_raw'],'link_from_raw_row_matrix':[list(r) for r in UsdGeom.Xformable(asset.GetPrimAtPath(visual)).GetLocalTransformation()],'topology_sha256':hashlib.sha256(np.asarray(mesh.GetAttribute('faceVertexIndices').Get()).tobytes()).hexdigest(),'geometry_sha256':sha(geo_file)}
asset.GetRootLayer().Save()
shutil.copy2(SCENE,TARGET)
new_layer=Sdf.Layer.FindOrOpen(str(TARGET))
root_spec=Sdf.CreatePrimInLayer(new_layer,'/World/Excavator')
root_spec.payloadList.explicitItems=[Sdf.Payload('../excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda')]
metadata=dict(new_layer.customLayerData)
metadata['meshReplacement']={'sourceScene':str(SCENE),'sourceSceneSha256':sha(SCENE),'meshAsset':str(ASSET),'bucketPolicy':'Preserve full teeth','manifest':str(BUNDLE/'manifest.json')}
if 'omni_layer' in metadata:
    metadata['omni_layer']=dict(metadata['omni_layer']);metadata['omni_layer']['authoring_layer']='./'+TARGET.name
new_layer.customLayerData=metadata;new_layer.Save()
assert all(sha(p)==h for p,h in source_hashes.items()),'Existing source changed during build'
manifest.update(asset=str(ASSET),asset_sha256=sha(ASSET),scene=str(TARGET),scene_sha256=sha(TARGET),total_vertices=sum(x['vertices'] for x in manifest['parts'].values()),total_faces=sum(x['faces'] for x in manifest['parts'].values()),source_files_unchanged=True)
dump(BUNDLE/'manifest.json',manifest);dump(WORK/'build_manifest.json',manifest)
print(json.dumps({'asset':str(ASSET),'scene':str(TARGET),'total_vertices':manifest['total_vertices'],'total_faces':manifest['total_faces'],'sources_unchanged':True,'alignment_max_source_units':max(r['max'] for r in evidence['gaussian_checks'].values())}))
