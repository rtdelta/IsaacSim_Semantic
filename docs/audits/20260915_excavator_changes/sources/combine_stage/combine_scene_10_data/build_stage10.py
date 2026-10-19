"""Build a new scene layer only. Never save a pre-existing source layer."""
import sys,json,hashlib,math
from pathlib import Path
import numpy as np
sys.path.insert(0,'/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Usd,Sdf,UsdGeom,UsdPhysics,UsdRender,Gf,Vt
B=Path('/root/gpufree-data/IsaacSim_Asset')
C=B/'combine_stage';OUT=C/'combine_scene_10_data';DEST=C/'combine_scene_10.usda'
OLD='/Excavator_Fangshan_03';NEW='/Excavator_Fangshan_05'
assert not DEST.exists(),f'Refusing to overwrite {DEST}'
cfg=json.loads((OUT/'kinematics.json').read_text());mounts=json.loads((OUT/'sensor_mounts.json').read_text())['mounts']
source=Sdf.Layer.FindOrOpen(str(C/'combine_scene_08.usda'))
before={}
# Record all existing USD/data/code inputs without touching their contents.
roots=[C,B/'excavator_module_set/Sim_Fangshan_02',B/'sensor_set',B/'environment_module_set/static_completed_environment_set']
for root in roots:
    for f in root.rglob('*'):
        if f.is_file() and 'combine_scene_10' not in str(f) and f.suffix.lower() in ('.usd','.usda','.usdc','.usdz','.py','.json','.mdl'):
            h=hashlib.sha256()
            with f.open('rb') as stream:
                for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
            before[str(f)]={'sha256':h.hexdigest(),'size':f.stat().st_size}
(OUT/'source_hashes_before.json').write_text(json.dumps(before,indent=2))
layer=Sdf.Layer.CreateNew(str(DEST));layer.TransferContent(source)
stage=Usd.Stage.Open(layer,load=Usd.Stage.LoadNone)
stage.RemovePrim(OLD);stage.RemovePrim('/Render')
root=UsdGeom.Xform.Define(stage,NEW).GetPrim()
root.GetVariantSets().AddVariantSet('visualization').SetVariantSelection('3dgs')
root.GetPayloads().AddPayload('../excavator_module_set/Sim_Fangshan_02/Excavator_Fangshan_05.usda')
root.SetDisplayName('Excavator Fangshan 05 | stage 10')
stage.Load(NEW)

def set_pose(prim,t,reset=False):
    x=UsdGeom.Xformable(prim)
    if reset:
        for a in list(prim.GetAttributes()):
            if a.GetName().startswith('xformOp:'):prim.RemoveProperty(a.GetName())
        x.ClearXformOpOrder()
        x.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)
        x.AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
        x.AddScaleOp(UsdGeom.XformOp.PrecisionDouble)
    prim.GetAttribute('xformOp:translate').Set(Gf.Vec3d(*t[:3,3]))
    quat=Gf.Matrix4d(*t.T.flatten().tolist()).ExtractRotationQuat()
    a=prim.GetAttribute('xformOp:orient')
    a.Set(Gf.Quatf(quat) if a.GetTypeName()==Sdf.ValueTypeNames.Quatf else quat)
    a=prim.GetAttribute('xformOp:scale')
    if a:a.Set(Gf.Vec3f(1) if a.GetTypeName()==Sdf.ValueTypeNames.Float3 else Gf.Vec3d(1))

for m in mounts:
    dest=m['proposed_mount_path'];Sdf.CreatePrimInLayer(layer,str(Sdf.Path(dest).GetParentPath()))
    assert Sdf.CopySpec(source,m['old_mount_path'],layer,dest)
    if m['name']!='MyOS0_up':set_pose(stage.GetPrimAtPath(dest),np.array(m['candidate_T_link_from_mount']),reset=False)

# Approximate the old folded visual orientation in the new URDF-angle convention.
# Project each relative rotation onto its permitted Z axis; never alter joint frames.
rotations={'base_link':np.eye(3)};angles={};transforms={'base_link':np.eye(4)}
links={r['urdf_link']:r for r in cfg['links']}
for j in cfg['joints']:
    desired=np.array(links[j['child']]['registration_rotation_source_to_link']).T
    origin=np.array(j['origin']['T_parent_from_local'])
    rel=(rotations[j['parent']]@origin[:3,:3]).T@desired
    angle=math.atan2(rel[1,0]-rel[0,1],rel[0,0]+rel[1,1])
    c,s=math.cos(angle),math.sin(angle);rz=np.eye(4);rz[:2,:2]=[[c,-s],[s,c]]
    transforms[j['child']]=transforms[j['parent']]@origin@rz
    rotations[j['child']]=transforms[j['child']][:3,:3]
    angles[j['name']]=math.degrees(angle)
    UsdPhysics.DriveAPI(stage.GetPrimAtPath(NEW+'/Joints/'+j['name']),'angular').GetTargetPositionAttr().Set(angles[j['name']])
for link in cfg['links']:set_pose(stage.GetPrimAtPath(NEW+'/'+link['body_name']),transforms[link['urdf_link']])

# Preserve old swing-axis XY. The original flat grid is world Z=0; use GS-centre
# track bounds plus 2 cm clearance as an explicit preview datum, not surveyed ground.
old_t=np.array([ -1.158813,1.580568075,.21875559227360208 ])
old_pin=np.array(cfg['source_pins_m'][0])
root_xyz=[float(old_t[0]+old_pin[0]),float(old_t[1]+old_pin[1]),float(-links['base_link']['registered_gs_center_bounds_link_m'][0][2]+.02)]
rt=np.eye(4);rt[:3,3]=root_xyz;set_pose(root,rt,reset=True)
root.SetCustomDataByKey('stage10:initialJointDegrees',Vt.DoubleArray([angles[n] for n in cfg['joint_order']]))
root.SetCustomDataByKey('stage10:mountPolicy','13 geometry-mapped mounts; MyOS0_up authored local transform unchanged; direct parent hierarchy preserved')
root.SetCustomDataByKey('stage10:groundDatum','Preview world Z=0 flat grid, GS-centre minimum + 0.02 m; not a terrain/contact calibration')
anchor=UsdPhysics.FixedJoint.Define(stage,'/World/Stage10BaseAnchor')
anchor.CreateBody1Rel().SetTargets([NEW+'/track_prim'])
anchor.CreateLocalPos0Attr().Set(Gf.Vec3f(*root_xyz));anchor.CreateLocalRot0Attr().Set(Gf.Quatf(1))
anchor.CreateLocalPos1Attr().Set(Gf.Vec3f(0));anchor.CreateLocalRot1Attr().Set(Gf.Quatf(1))
anchor.GetPrim().SetCustomDataByKey('purpose','Scene-only preview anchor; standalone 05 remains reusable and unanchored')

# Persistent products: one device, one product, no old transient SDGPipeline overs.
UsdGeom.Scope.Define(stage,'/Render');UsdGeom.Scope.Define(stage,'/Render/Vars');UsdGeom.Scope.Define(stage,'/Render/Products')
for name,dt in [('LdrColor','color4f'),('GenericModelOutput','uchar')]:
    v=UsdRender.Var.Define(stage,'/Render/Vars/'+name);v.CreateSourceNameAttr(name);v.CreateSourceTypeAttr('raw');v.CreateDataTypeAttr(dt)
settings=UsdRender.Settings.Define(stage,'/Render/Settings');products=[]
for m in mounts:
    path='/Render/Products/'+m['name'];rp=UsdRender.Product.Define(stage,path)
    rp.CreateCameraRel().SetTargets([m['proposed_sensor_path']]);rp.CreateResolutionAttr(Gf.Vec2i(1280,720) if m['name']=='Camera' else Gf.Vec2i(300,300))
    rp.CreateOrderedVarsRel().SetTargets(['/Render/Vars/'+('LdrColor' if m['name']=='Camera' else 'GenericModelOutput')])
    rp.CreateProductNameAttr(m['name']);rp.CreateProductTypeAttr('raster')
    rp.GetPrim().SetCustomDataByKey('stage10:frameId',m['name'])
    products.append(path);m['render_product_path']=path;m['frame_id']=m['name']
settings.CreateProductsRel().SetTargets(products);stage.SetMetadata('renderSettingsPrimPath','/Render/Settings')

# Add a convenient overview camera without changing the sensor camera's optics.
cam=UsdGeom.Camera.Define(stage,'/World/Stage10Overview')
view=Gf.Matrix4d().SetLookAt(Gf.Vec3d(13,-17,13),Gf.Vec3d(1,1,2.6),Gf.Vec3d(0,0,1))
UsdGeom.Xformable(cam).AddTransformOp().Set(view.GetInverse());cam.CreateFocalLengthAttr(30)
cam.CreateClippingRangeAttr(Gf.Vec2f(.05,10000))
cld=layer.customLayerData
cld['stage10']={'sourceScene':'combine_scene_08.usda','excavatorPayload':'Excavator_Fangshan_05.usda','initialPosePolicy':'Fit old folded orientation; joint zero frames unchanged','openWithoutStartupScript':True}
if 'cameraSettings' in cld:cld['cameraSettings']['boundCamera']='/World/Stage10Overview'
layer.customLayerData=cld
layer.Save()
manifest={'scene':str(DEST),'root_path':NEW,'articulation_root':NEW+'/track_prim','joint_paths':{n:NEW+'/Joints/'+n for n in cfg['joint_order']},'joint_order':cfg['joint_order'],'initial_joint_degrees':angles,'root_translation_m':root_xyz,'root_scale':[1,1,1],'visualization':'3dgs','source_count':len(before),'sensors':mounts,'geometry_scale_xyz':[2.4]*3,'ground_policy':'world grid Z=0 + 2cm GS-centre clearance; no physical contact or terrain fitting','base_anchor':'/World/Stage10BaseAnchor','csv_player_migrated':False}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'created':str(DEST),'sensor_count':len(mounts),'initial_joint_degrees':angles,'root_translation_m':root_xyz,'hashed_source_files':len(before)}))
