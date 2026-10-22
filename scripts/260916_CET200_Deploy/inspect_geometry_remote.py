from pathlib import Path
import sys
import numpy as np
import xml.etree.ElementTree as ET
sys.path.insert(0, '/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312')
from pxr import Usd, UsdGeom
r = Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200')
s = Usd.Stage.Open(str(r/'usd/CET200.usda'))
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default','render'])
for p in s.Traverse():
    if p.GetName() in ['TF_Origin','RB_UpperStructure','RB_Boom','RB_Arm','RB_Bucket']:
        print('BODY',str(p.GetPath()),str(cache.ComputeLocalBound(p).ComputeAlignedRange()))
meshes=[p for p in Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh)]
print('MESH_COUNT',len(meshes))
for p in meshes:
    if 'RB_Boom/' in str(p.GetPath()) and '/RB_Arm/' not in str(p.GetPath()):
        print('MESH',str(p.GetPath()),'EXTENT',UsdGeom.Mesh(p).GetExtentAttr().Get(),
              'WORLD_MATRIX',str(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default())))
ns={'c':'http://www.collada.org/2005/11/COLLADASchema'}
for name in ['boom','upper_structure','arm','track_frame']:
    x=ET.parse(r/('source/cet200_description/meshes/'+name+'.dae')).getroot()
    geometries={g.get('id'):g for g in x.findall('c:library_geometries/c:geometry',ns)}
    points=[]
    def walk(node,parent):
        m=node.find('c:matrix',ns)
        local=np.array(list(map(float,m.text.split()))).reshape(4,4) if m is not None else np.eye(4)
        world=parent@local
        for inst in node.findall('c:instance_geometry',ns):
            g=geometries[inst.get('url')[1:]]
            for src in g.findall('c:mesh/c:source',ns):
                if 'position' in src.get('id',''):
                    a=np.array(list(map(float,src.find('c:float_array',ns).text.split()))).reshape(-1,3)
                    q=np.c_[a,np.ones(len(a))]@world.T
                    points.append(q[:,:3])
        for child in node.findall('c:node',ns): walk(child,world)
    for n in x.findall('c:library_visual_scenes/c:visual_scene/c:node',ns): walk(n,np.eye(4))
    v=np.concatenate(points)
    print('DAE_EXPECTED_BOUNDS',name,v.min(0).tolist(),v.max(0).tolist())
