"""Check the pure scale, joint convention and reusable payload path remapping."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Sdf, Usd, UsdGeom, UsdPhysics
folder=Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02')
target=folder/'Excavator_Fangshan_05_origin03.usda'
mask=Usd.StagePopulationMask()
for name in ['track_prim/Visuals/GS/__probe__','track_prim/Visuals/Mesh/__probe__','Joints']:
    mask.Add('/Excavator/'+name)
stage=Usd.Stage.OpenMasked(str(target),mask)
assert stage.GetDefaultPrim().GetPath()==Sdf.Path('/Excavator')
for group in ('GS','Mesh'):
    xf=UsdGeom.Xformable(stage.GetPrimAtPath('/Excavator/track_prim/Visuals/'+group))
    np.testing.assert_allclose(np.array(xf.GetLocalTransformation()),np.diag([2.4,2.4,2.4,1]),atol=1e-12)
old=Usd.Stage.OpenMasked(str(folder/'Excavator_Fangshan_05.usda'),mask)
for name in ('swing','boom','arm','bucket'):
    a=old.GetPrimAtPath('/Excavator/Joints/'+name); b=stage.GetPrimAtPath('/Excavator/Joints/'+name)
    for attr in a.GetAuthoredAttributes():
        if name=='swing' and attr.GetName()=='physics:localPos0':continue
        assert attr.Get()==b.GetAttribute(attr.GetName()).Get(),(name,attr.GetName())
test=Usd.Stage.CreateInMemory(load=Usd.Stage.LoadNone)
newmask=Usd.StagePopulationMask()
for name in ('A','B'):
    UsdGeom.Xform.Define(test,'/'+name).GetPrim().GetPayloads().AddPayload(str(target))
    newmask.Add('/'+name+'/Joints')
test.SetPopulationMask(newmask)
test.Load()
for name in ('A','B'):
    for j in ('swing','boom','arm','bucket'):
        p=UsdPhysics.Joint(test.GetPrimAtPath('/'+name+'/Joints/'+j))
        for rel in (p.GetBody0Rel(),p.GetBody1Rel()):
            assert all(str(x).startswith('/'+name+'/') for x in rel.GetTargets())
report={'passed':True,'track_geometry_transform':'diag(2.4,2.4,2.4,1)',
        'joint_attributes_preserved_except_swing_parent_position':True,
        'two_payload_instances_remap_joint_targets':True}
(folder/'Excavator_Fangshan_05_origin03_data/payload_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
