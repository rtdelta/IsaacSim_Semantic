"""Compare final USD geometry and joint anchors with original URDF/DAE data."""
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0,'/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Gf, Usd, UsdGeom, UsdPhysics

ROOT=Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200')
SOURCE=ROOT/'source/cet200_description'
NS={'c':'http://www.collada.org/2005/11/COLLADASchema'}


def transform(el):
    T=np.eye(4)
    if el is None:return T
    T[:3,3]=list(map(float,el.get('xyz','0 0 0').split()))
    r,p,y=map(float,el.get('rpy','0 0 0').split())
    cr,sr,cp,sp,cy,sy=math.cos(r),math.sin(r),math.cos(p),math.sin(p),math.cos(y),math.sin(y)
    T[:3,:3]=np.array([[cy,-sy,0],[sy,cy,0],[0,0,1]])@np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]])@np.array([[1,0,0],[0,cr,-sr],[0,sr,cr]])
    return T


def dae_points(path):
    root=ET.parse(path).getroot()
    geos={g.get('id'):g for g in root.findall('c:library_geometries/c:geometry',NS)}
    unit=float(root.find('c:asset/c:unit',NS).get('meter','1'))
    points=[]
    def walk(node,parent):
        local=np.eye(4)
        for m in node.findall('c:matrix',NS):local=local@np.array(list(map(float,m.text.split()))).reshape(4,4)
        world=parent@local
        for inst in node.findall('c:instance_geometry',NS):
            g=geos[inst.get('url')[1:]]
            vertices=g.find('c:mesh/c:vertices',NS)
            pos=next(i.get('source')[1:] for i in vertices.findall('c:input',NS) if i.get('semantic')=='POSITION')
            src=next(s for s in g.findall('c:mesh/c:source',NS) if s.get('id')==pos)
            a=np.array(list(map(float,src.find('c:float_array',NS).text.split()))).reshape(-1,3)
            points.append((np.c_[a,np.ones(len(a))]@world.T)[:,:3]*unit)
        for child in node.findall('c:node',NS):walk(child,world)
    for n in root.findall('c:library_visual_scenes/c:visual_scene/c:node',NS):walk(n,np.eye(4))
    return np.concatenate(points)


urdf=ET.parse(SOURCE/'urdf/cet200.urdf').getroot()
joints=urdf.findall('joint')
children={j.find('child').get('link') for j in joints}
roots=[l.get('name') for l in urdf.findall('link') if l.get('name') not in children]
assert len(roots)==1
worlds={roots[0]:np.eye(4)}
while len(worlds)<len(urdf.findall('link')):
    old=len(worlds)
    for j in joints:
        parent=j.find('parent').get('link');child=j.find('child').get('link')
        if parent in worlds:worlds[child]=worlds[parent]@transform(j.find('origin'))
    assert len(worlds)>old
expected=[]
for link in urdf.findall('link'):
    for visual in link.findall('visual'):
        mesh=visual.find('geometry/mesh')
        assert mesh is not None
        path=SOURCE/mesh.get('filename').split('package://cet200_description/',1)[1]
        a=dae_points(path)*np.array(list(map(float,mesh.get('scale','1 1 1').split())))
        T=worlds[link.get('name')]@transform(visual.find('origin'))
        expected.append((np.c_[a,np.ones(len(a))]@T.T)[:,:3])
expected=np.concatenate(expected)
stage=Usd.Stage.Open(str(ROOT/'usd/CET200.usda'))
actual=[]
for prim in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()):
    if not prim.IsA(UsdGeom.Mesh):continue
    img=UsdGeom.Imageable(prim)
    if img.ComputePurpose() not in ('default','render') or img.ComputeVisibility()=='invisible':continue
    a=np.array(UsdGeom.Mesh(prim).GetPointsAttr().Get())
    T=np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
    actual.append((np.c_[a,np.ones(len(a))]@T.T)[:,:3])
actual=np.concatenate(actual)
eb=np.array([expected.min(0),expected.max(0)]);ab=np.array([actual.min(0),actual.max(0)])
error=float(np.max(np.abs(eb-ab)))
report={'original_visual_bounds_m':eb.tolist(),'usd_visual_bounds_m':ab.tolist(),
        'max_bounds_difference_m':error,'original_vertex_count':len(expected),'usd_vertex_count':len(actual),
        'joints':{}}
assert error<2e-5,report
for name in ('Hinge_Slew','Hinge_Boom','Hinge_Arm','Hinge_Bucket'):
    src=next(j for j in joints if j.get('name')==name)
    child=src.find('child').get('link')
    joint=UsdPhysics.RevoluteJoint(stage.GetPrimAtPath('/CET200/Physics/'+name))
    body=stage.GetPrimAtPath(joint.GetBody0Rel().GetTargets()[0])
    bodyT=UsdGeom.Xformable(body).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    pos=bodyT.Transform(Gf.Vec3d(joint.GetLocalPos0Attr().Get()))
    delta=float(np.linalg.norm(np.array(pos)-worlds[child][:3,3]))
    axis=np.array(list(map(float,src.find('axis').get('xyz').split())))
    basis={'X':Gf.Vec3d(1,0,0),'Y':Gf.Vec3d(0,1,0),'Z':Gf.Vec3d(0,0,1)}[joint.GetAxisAttr().Get()]
    localR=Gf.Matrix4d().SetRotate(Gf.Quatd(joint.GetLocalRot0Attr().Get()))
    axis_actual=np.array((localR*bodyT).TransformDir(basis))
    axis_expected=worlds[child][:3,:3]@axis
    np.testing.assert_allclose(axis_actual,axis_expected,atol=1e-6)
    assert delta<1e-5,(name,delta)
    report['joints'][name]={'anchor_error_m':delta,'axis_world':axis_actual.tolist()}
assert subprocess.check_output(['git','-C',str(ROOT/'source'),'status','--porcelain'],text=True)==''
report['upstream_unmodified']=True
report['passed']=True
(ROOT/'reports/geometry_audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
