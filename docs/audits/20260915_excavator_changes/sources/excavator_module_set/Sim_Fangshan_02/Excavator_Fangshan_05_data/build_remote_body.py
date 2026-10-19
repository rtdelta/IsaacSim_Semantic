"""Build only the new 05 files. CONFIG is injected by the local preparation step."""
import sys,json,hashlib,math,os
from pathlib import Path
import numpy as np
sys.path.insert(0,'/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Usd,UsdGeom,UsdPhysics,UsdShade,UsdLux,UsdRender,Gf,Sdf,Vt
FOLDER=Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02')
ASSET=FOLDER/'Excavator_Fangshan_05.usda'
DATA=FOLDER/'Excavator_Fangshan_05_data'
PREVIEW=FOLDER/'Excavator_Fangshan_05_preview.usda'
assert not ASSET.exists() and not DATA.exists() and not PREVIEW.exists(),'05 output already exists; refusing to overwrite'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
originals={str(p.relative_to(FOLDER)):sha(p) for p in FOLDER.rglob('*') if p.is_file()}
assert originals['Excavator_Fangshan_03.usda']=='dc81e1ce2153975e7cbcfc3bf63e68d403b1332197b81cccaf9b7ac16c8218a6'
assert originals['Excavator_Fangshan_04.usda']==CONFIG['source04_sha256']
DATA.mkdir()
def gm(t):return Gf.Matrix4d(*np.asarray(t,dtype=float).T.flatten().tolist())
def cm(t):return np.asarray(t,dtype=float).T
def quat(r):
    m=np.eye(4);m[:3,:3]=r;q=gm(m).ExtractRotationQuat()
    return Gf.Quatf(float(q.GetReal()),Gf.Vec3f(*q.GetImaginary()))
def set_pose(p,t):
    x=UsdGeom.Xformable(p);x.ClearXformOpOrder()
    x.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*np.array(t)[:3,3]))
    x.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(gm(t).ExtractRotationQuat())
def mat_attr(p,t):
    t=np.array(t,dtype=float); r=t.copy();r[:3,:3]/=2.4;r[:3,3]=0
    x=UsdGeom.Xformable(p)
    x.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*t[:3,3]))
    x.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(gm(r).ExtractRotationQuat())
    x.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(2.4))
    p.SetCustomData({'uniformScaleFrom03':2.4, 'registrationPolicy':'Source hinge anchored; URDF zero-direction rotation retained'})
def metadata(st):
    UsdGeom.SetStageMetersPerUnit(st,1);UsdGeom.SetStageUpAxis(st,UsdGeom.Tokens.z)
    UsdPhysics.SetStageKilogramsPerUnit(st,1)

# Small exact URDF mesh reference, generated as a separate new USD layer.
refstage=Usd.Stage.CreateNew(str(DATA/'urdf_reference_meshes.usdc'));metadata(refstage)
rr=UsdGeom.Xform.Define(refstage,'/URDFReference');refstage.SetDefaultPrim(rr.GetPrim())
for row in CONFIG['links']:
    data=row['reference_mesh'];m=UsdGeom.Mesh.Define(refstage,'/URDFReference/'+row['urdf_link'])
    pts=np.array(data['points_link'],dtype=float)
    m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(pts.astype(np.float32)))
    m.CreateFaceVertexCountsAttr(data['face_vertex_counts']);m.CreateFaceVertexIndicesAttr(data['face_vertex_indices'])
    m.CreateSubdivisionSchemeAttr('none');m.CreateDoubleSidedAttr(True)
    m.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*pts.min(0)),Gf.Vec3f(*pts.max(0))]))
refstage.GetRootLayer().Save()

stage=Usd.Stage.CreateNew(str(ASSET));metadata(stage)
root=UsdGeom.Xform.Define(stage,'/Excavator').GetPrim();stage.SetDefaultPrim(root)
root.SetMetadata('kind','component');root.SetDisplayName('Excavator Fangshan 05 - uniform 2.4 / URDF angle rules')
root.SetCustomData({'version':'05','urdfSourceSha256':CONFIG['urdf_source']['sha256'],
 'jointOrder':Vt.StringArray(CONFIG['joint_order']),
 'angleConvention':'URDF radians in control interfaces; USD angular drive properties are degrees',
 'scope':CONFIG['policy'],
 'loadMode':'USD Payload / no startup scripts or external application callbacks required', 'uniformScaleFrom03':2.4, 'baseOriginPolicy':CONFIG['base_origin_policy'], 'referenceVisualPolicy':CONFIG['reference_visual_policy']})
materials={}
for name,color in zip(['base_link','swing_link','boom_link','arm_link','bucket_link'],[(.22,.28,.35),(.53,.49,.37),(.95,.55,.055),(.05,.51,.61),(.44,.21,.62)]):
    mat=UsdShade.Material.Define(stage,'/Excavator/Looks/'+name)
    shader=UsdShade.Shader.Define(stage,str(mat.GetPath())+'/Surface');shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.65)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface');materials[name]=mat
link_paths={}
source_to_bodies={}
for row in CONFIG['links']:
    lname=row['urdf_link'];bpath='/Excavator/'+row['body_name'];link_paths[lname]=bpath
    body=UsdGeom.Xform.Define(stage,bpath).GetPrim();body.SetDisplayName(lname)
    body.SetCustomData({'urdfLink':lname,'source03Body':row['body_name'],'dynamicsStatus':'placeholder retained in spirit from 03; not calibrated'})
    set_pose(body,np.array(row['T_base_from_link_zero']))
    UsdPhysics.RigidBodyAPI.Apply(body)
    mass=UsdPhysics.MassAPI.Apply(body);mass.CreateMassAttr(1.);mass.CreateCenterOfMassAttr(Gf.Vec3f(0))
    mass.CreateDiagonalInertiaAttr(Gf.Vec3f(1));mass.CreatePrincipalAxesAttr(Gf.Quatf(1))
    schemas=list(body.GetAppliedSchemas())+['PhysxRigidBodyAPI'];body.SetMetadata('apiSchemas',Sdf.TokenListOp.CreateExplicit(schemas))
    body.CreateAttribute('physxRigidBody:disableGravity',Sdf.ValueTypeNames.Bool,custom=False).Set(True)
    if lname=='base_link':UsdPhysics.ArticulationRootAPI.Apply(body)
    visual=UsdGeom.Xform.Define(stage,bpath+'/Visuals').GetPrim()
    for group in ['GS','Mesh']:
        p=UsdGeom.Xform.Define(stage,bpath+'/Visuals/'+group).GetPrim()
        mat_attr(p,np.array(row['T_link_from_source_geometry']))
    gs=bpath+'/Visuals/GS'
    files=[row['source_part']] if lname!='bucket_link' else ['bucket_without_teeth']+[f'tooth_{i:02d}_{side}' for i in range(1,6) for side in ['front','back']]
    for name in files:
        gp=stage.DefinePrim(gs+'/'+name)
        gp.GetPayloads().AddPayload('./3dgs_usd/'+name+'.usd')
    mp=stage.DefinePrim(bpath+'/Visuals/Mesh/source_mesh')
    source=row['source_part']
    mp.GetReferences().AddReference('./waji_mesh_corrected.usdc','/root/'+source+'_mesh/'+source+'_mesh')
    UsdShade.MaterialBindingAPI.Apply(mp).Bind(materials[lname])
    up=stage.DefinePrim(bpath+'/Visuals/URDFReference')
    up.GetReferences().AddReference('./Excavator_Fangshan_05_data/urdf_reference_meshes.usdc','/URDFReference/'+lname)
    UsdShade.MaterialBindingAPI.Apply(up).Bind(materials[lname])

UsdGeom.Scope.Define(stage,'/Excavator/Joints')
for j in CONFIG['joints']:
    joint=UsdPhysics.RevoluteJoint.Define(stage,'/Excavator/Joints/'+j['name'])
    joint.CreateBody0Rel().SetTargets([link_paths[j['parent']]])
    joint.CreateBody1Rel().SetTargets([link_paths[j['child']]])
    joint.CreateAxisAttr('Z');joint.CreateLocalPos0Attr(Gf.Vec3f(*j['origin']['xyz_m']))
    joint.CreateLocalRot0Attr(quat(np.array(j['origin']['T_parent_from_local'])[:3,:3]))
    joint.CreateLocalPos1Attr(Gf.Vec3f(0));joint.CreateLocalRot1Attr(Gf.Quatf(1))
    joint.CreateJointEnabledAttr(True);joint.CreateCollisionEnabledAttr(False)
    # Continuous in the reference; do not copy the invalid reversed URDF limits.
    joint.GetPrim().SetCustomData({'urdfJointType':'continuous','referenceAxis':'0 0 1','limitPolicy':'unbounded continuous; invalid reversed URDF lower/upper omitted'})
    drive=UsdPhysics.DriveAPI.Apply(joint.GetPrim(),'angular')
    drive.CreateTypeAttr('force');drive.CreateTargetPositionAttr(0.);drive.CreateTargetVelocityAttr(0.)
    drive.CreateStiffnessAttr(10000.);drive.CreateDampingAttr(200.);drive.CreateMaxForceAttr(100000.)
    joint.GetPrim().CreateAttribute('userProperties:drivePurpose',Sdf.ValueTypeNames.String).Set('Pose preview only; not a real hydraulic actuator calibration')

variants=root.GetVariantSets().AddVariantSet('visualization')
for choice,group in [('3dgs','GS'),('source_mesh','Mesh'),('urdf_reference','URDFReference')]:
    variants.AddVariant(choice);variants.SetVariantSelection(choice)
    with variants.GetVariantEditContext():
        for row in CONFIG['links']:
            for g in ['GS','Mesh','URDFReference']:
                UsdGeom.Imageable(stage.GetPrimAtPath('/Excavator/'+row['body_name']+'/Visuals/'+g)).CreateVisibilityAttr('inherited' if g==group else 'invisible')
variants.SetVariantSelection('3dgs')
stage.GetRootLayer().Save()

# A convenience scene. The actual payload asset has no scene, lights, camera, or scripts.
pv=Usd.Stage.CreateNew(str(PREVIEW));metadata(pv)
w=UsdGeom.Xform.Define(pv,'/World').GetPrim();pv.SetDefaultPrim(w)
rp=UsdGeom.Xform.Define(pv,'/World/Excavator05').GetPrim();rp.GetPayloads().AddPayload('./Excavator_Fangshan_05.usda')
light=UsdLux.DomeLight.Define(pv,'/World/Light');light.CreateIntensityAttr(700.)
camera=UsdGeom.Camera.Define(pv,'/World/Camera')
camera.CreateClippingRangeAttr(Gf.Vec2f(.01,1000.));camera.CreateFocalLengthAttr(26.)
view=Gf.Matrix4d().SetLookAt(Gf.Vec3d(14,-23,12),Gf.Vec3d(3.5,-0.3,1.4),Gf.Vec3d(0,0,1))
UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse())
pv.GetRootLayer().customLayerData={'cameraSettings':{'boundCamera':'/World/Camera'}}
scene=UsdPhysics.Scene.Define(pv,'/World/PhysicsScene');scene.CreateGravityMagnitudeAttr(0.)
support=UsdPhysics.FixedJoint.Define(pv,'/World/PreviewBaseSupport')
support.CreateBody1Rel().SetTargets(['/World/Excavator05/track_prim'])
support.CreateLocalPos0Attr(Gf.Vec3f(0));support.CreateLocalPos1Attr(Gf.Vec3f(0))
support.CreateLocalRot0Attr(Gf.Quatf(1));support.CreateLocalRot1Attr(Gf.Quatf(1))
support.GetPrim().SetCustomData({'purpose':'Preview scene only; payload asset itself remains unfixed'})
pv.GetRootLayer().Save()

# Validate a payload below an unrelated path, with a non-identity parent transform.
test=Usd.Stage.CreateInMemory();metadata(test)
container=UsdGeom.Xform.Define(test,'/TestParent');tt=Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0,0,1),37));tt.SetTranslateOnly(Gf.Vec3d(23,-11,4));container.AddTransformOp().Set(tt)
for name in ['RobotA','RobotB']:
    p=UsdGeom.Xform.Define(test,'/TestParent/'+name).GetPrim();p.GetPayloads().AddPayload(str(ASSET))
assert not test.GetCompositionErrors(),[str(e) for e in test.GetCompositionErrors()]
xc=UsdGeom.XformCache();zero_err=[];axis_err=[]
for instance in ['RobotA','RobotB']:
    prefix='/TestParent/'+instance
    root_t=cm(xc.GetLocalToWorldTransform(test.GetPrimAtPath(prefix)))
    for row in CONFIG['links']:
        got=np.linalg.inv(root_t)@cm(xc.GetLocalToWorldTransform(test.GetPrimAtPath(prefix+'/'+row['body_name'])))
        zero_err.append(float(np.max(abs(got-np.array(row['T_base_from_link_zero'])))))
    for j in CONFIG['joints']:
        p=test.GetPrimAtPath(prefix+'/Joints/'+j['name']);joint=UsdPhysics.RevoluteJoint(p)
        for rel in [joint.GetBody0Rel(),joint.GetBody1Rel()]:assert all(str(x).startswith(prefix+'/') for x in rel.GetTargets())
        body0=test.GetPrimAtPath(joint.GetBody0Rel().GetTargets()[0]);t0=np.linalg.inv(root_t)@cm(xc.GetLocalToWorldTransform(body0))
        q=joint.GetLocalRot0Attr().Get();r=cm(Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Quatd(q))))[:3,:3]
        axis_err.append(float(np.linalg.norm(t0[:3,:3]@r@np.array([0,0,1.])-np.array(j['zero_axis_in_base']))))
assert max(zero_err)<1e-12
assert max(axis_err)<2e-7
def joint_frame(joint,side):
    p=getattr(joint,f'GetLocalPos{side}Attr')().Get();q=getattr(joint,f'GetLocalRot{side}Attr')().Get()
    t=cm(Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Quatd(q))));t[:3,3]=p;return t
states=[np.zeros(4)]
for k in range(4):
    for deg in [-30,-10,10,30]:
        q=np.zeros(4);q[k]=math.radians(deg);states.append(q)
states.extend(np.random.default_rng(4).uniform(-1,1,(12,4)))
fk_errors=[]
for q in states:
    actual={'base_link':np.eye(4)};expected={'base_link':np.eye(4)}
    for k,j in enumerate(CONFIG['joints']):
        c,s=math.cos(q[k]),math.sin(q[k]);motion=np.eye(4);motion[:2,:2]=[[c,-s],[s,c]]
        joint=UsdPhysics.RevoluteJoint(stage.GetPrimAtPath('/Excavator/Joints/'+j['name']))
        actual[j['child']]=actual[j['parent']]@joint_frame(joint,0)@motion@np.linalg.inv(joint_frame(joint,1))
        expected[j['child']]=expected[j['parent']]@np.array(j['origin']['T_parent_from_local'])@motion
        fk_errors.append(float(np.max(abs(actual[j['child']]-expected[j['child']]))))
assert max(fk_errors)<3e-6,max(fk_errors)
active_gs=[p for p in stage.Traverse() if p.GetTypeName()=='ParticleField3DGaussianSplat']
assert len(active_gs)==15,len(active_gs)
for choice in variants.GetVariantNames():
    variants.SetVariantSelection(choice)
    assert not stage.GetCompositionErrors()
variants.SetVariantSelection('3dgs');stage.GetRootLayer().Save()
assert not stage.GetCompositionErrors()
# Verify full composed GS transforms, source pin closure, and per-part dimensions.
xc=UsdGeom.XformCache()
uniform_checks=[]; full_dimensions=[]; anchor_checks=[]
for row in CONFIG['links']:
    bpath='/Excavator/'+row['body_name']
    for group in ['GS','Mesh']:
        p=stage.GetPrimAtPath(bpath+'/Visuals/'+group)
        local=cm(UsdGeom.Xformable(p).GetLocalTransformation())
        np.testing.assert_allclose(local,np.array(row['T_link_from_source_geometry']),atol=1e-12)
        sv=np.linalg.svd(cm(xc.GetLocalToWorldTransform(p))[:3,:3],compute_uv=False)
        np.testing.assert_allclose(sv,[2.4]*3,atol=1e-12)
        uniform_checks.append({'path':str(p.GetPath()),'world_singular_values':sv.tolist(),'authored_scale':list(p.GetAttribute('xformOp:scale').Get())})
    groups=[]
    for p in stage.Traverse():
        if p.GetTypeName()=='ParticleField3DGaussianSplat' and str(p.GetPath()).startswith(bpath+'/Visuals/GS/'):
            w=cm(xc.GetLocalToWorldTransform(p));sv=np.linalg.svd(w[:3,:3],compute_uv=False)
            np.testing.assert_allclose(sv,[2.4]*3,atol=1e-12)
            source=np.array(p.GetAttribute('positions').Get(),dtype=float)
            local=np.linalg.inv(cm(xc.GetLocalToWorldTransform(stage.GetPrimAtPath(bpath))))@w
            groups.append(source@local[:3,:3].T+local[:3,3])
    points=np.concatenate(groups)
    full_dimensions.append({'link':row['urdf_link'],'gaussian_count':len(points),'bounds_link_m':[points.min(0).tolist(),points.max(0).tolist()],'span_link_m':np.ptp(points,axis=0).tolist()})
for j in CONFIG['joints']:
    joint=UsdPhysics.RevoluteJoint(stage.GetPrimAtPath('/Excavator/Joints/'+j['name']))
    pin=np.array([*j['source_pin_m'],1.]); anchors=[]; frames=[]
    for side in [0,1]:
        bp=getattr(joint,f'GetBody{side}Rel')().GetTargets()[0]
        bt=cm(xc.GetLocalToWorldTransform(stage.GetPrimAtPath(bp)))
        gp=stage.GetPrimAtPath(str(bp)+'/Visuals/GS')
        anchors.append((cm(xc.GetLocalToWorldTransform(gp))@pin)[:3])
        frames.append(bt@joint_frame(joint,side))
    e=float(np.linalg.norm(anchors[0]-anchors[1]));fe=float(np.linalg.norm(frames[0][:3,3]-frames[1][:3,3]))
    ge=max(float(np.linalg.norm(a-f[:3,3])) for a,f in zip(anchors,frames))
    assert e<1e-11 and fe<1e-6 and ge<1e-6,(j['name'],e,fe,ge)
    anchor_checks.append({'joint':j['name'],'geometry_pin_separation_m':e,'joint_frame_separation_m':fe,'geometry_to_joint_error_m':ge,'pivot_base_m':anchors[0].tolist()})

after={n:sha(FOLDER/n) for n in originals}
assert originals==after,'An original file changed'
report={'uniform_scale':2.4,'uniform_scale_checks':uniform_checks,'full_gaussian_dimensions':full_dimensions,'anchor_checks':anchor_checks,'passed':True,'asset':str(ASSET),'preview_scene':str(PREVIEW),'default_prim':'/Excavator','visualization_default':'3dgs',
 'visualization_variants':variants.GetVariantNames(),'body_count':5,'joint_count':4,'gaussian_part_count':len(active_gs),
 'max_zero_transform_error':max(zero_err),'max_axis_error':max(axis_err),'payload_instances_tested':2,
 'fk_reference_policy':'05 scaled-source joint translations with URDF angular rules', 'fk_reference_states_tested':len(states),'fk_max_matrix_element_error':max(fk_errors),
 'payload_joint_targets_remap_correctly':True,'composition_errors':[],
 'original_files_checked':len(originals),'original_files_unchanged':True,'source_original_hashes':originals,
 'no_runtime_scripts_required':True,'dynamics':'placeholder, with pose-preview drives; not calibrated',
 'visual_dimension_policy':CONFIG['policy'],'registration':[{k:v for k,v in r.items() if k!='reference_mesh'} for r in CONFIG['links']]}
(DATA/'build_config.json').write_text(json.dumps(CONFIG,ensure_ascii=False,indent=2))
(DATA/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'passed':True,'asset':str(ASSET),'originals_checked':len(originals),'max_zero_transform_error':max(zero_err),'max_axis_error':max(axis_err),'fk_max_matrix_element_error':max(fk_errors),'anchor_checks':anchor_checks,'dimensions':full_dimensions},ensure_ascii=False,indent=2))
