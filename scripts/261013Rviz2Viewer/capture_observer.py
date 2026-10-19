"""Observe already accepted single06 data; export exact mesh/body coordinates."""
import hashlib, json, time
from pathlib import Path
import numpy as np

def write_stl(path, triangles):
    triangles = np.ascontiguousarray(triangles,dtype='<f4')
    normal = np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    normal /= np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-30)
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    rows=np.zeros(len(triangles),dtype=dtype)
    rows['normal']=normal; rows['vertices']=triangles
    with path.open('xb') as f:
        f.write(b'Exact captured USD geometry, scale baked into body coordinates'.ljust(80,b' '))
        f.write(np.asarray([len(rows)],dtype='<u4').tobytes());f.write(rows.tobytes())
    return hashlib.sha256(path.read_bytes()).hexdigest()

def export_asset(scene, directory):
    from pxr import UsdGeom, UsdPhysics, Gf
    binding=scene.config['robot_binding']
    paths={'track_link':binding['base_body']}
    paths.update({role+'_link':binding['joints'][role]['body1'] for role in ('swing','boom','arm','bucket')})
    cache=UsdGeom.XformCache();parts={};directory.mkdir(parents=True,exist_ok=False)
    for name,body_path in paths.items():
        body=np.asarray(cache.GetLocalToWorldTransform(scene.stage.GetPrimAtPath(body_path)),dtype=float)
        if not np.allclose(body[:3,:3].T@body[:3,:3],np.eye(3),atol=1e-5):
            raise ValueError('Nonrigid body pose; cannot silently discard scale: '+name)
        triangles=[];sources=[]
        for prim in scene.stage.Traverse():
            path=str(prim.GetPath())
            if not path.startswith(body_path+'/') or not prim.IsA(UsdGeom.Mesh):continue
            if any(path.startswith(other+'/') for other in paths.values() if other!=body_path and other.startswith(body_path+'/')):continue
            imageable=UsdGeom.Imageable(prim)
            if imageable.ComputeVisibility()=='invisible' or imageable.ComputePurpose()=='guide':continue
            mesh=UsdGeom.Mesh(prim);points=np.asarray(mesh.GetPointsAttr().Get(),dtype=float)
            counts=np.asarray(mesh.GetFaceVertexCountsAttr().Get(),dtype=int);indices=np.asarray(mesh.GetFaceVertexIndicesAttr().Get(),dtype=int)
            transform=np.asarray(cache.GetLocalToWorldTransform(prim))@np.linalg.inv(body)
            baked=(np.c_[points,np.ones(len(points))]@transform)[:,:3]
            if np.all(counts==3): tri=indices.reshape(-1,3)
            else:
                tri=[];offset=0
                for count in counts:
                    face=indices[offset:offset+count]
                    for i in range(1,count-1):tri.append([face[0],face[i],face[i+1]])
                    offset+=count
                tri=np.asarray(tri,dtype=int).reshape(-1,3)
            triangles.append(baked[tri]);sources.append({'prim':path,'triangles':len(tri),'mesh_to_body_row':transform.tolist()})
        if not triangles:raise ValueError('No visible mesh for '+name)
        value=np.concatenate(triangles);file=name+'.stl'
        parts[name]={'body_prim':body_path,'mesh':file,'sha256':write_stl(directory/file,value),'triangles':len(value),'body_bind_world_row':body.tolist(),'sources':sources,'local_bounds_m':[value.reshape(-1,3).min(0).tolist(),value.reshape(-1,3).max(0).tolist()]}
    joints=[]
    for role in ('swing','boom','arm','bucket'):
        item=binding['joints'][role];joint=UsdPhysics.RevoluteJoint(scene.stage.GetPrimAtPath(item['path']))
        anchors=[]
        for pos,quat in ((joint.GetLocalPos0Attr().Get(),joint.GetLocalRot0Attr().Get()),(joint.GetLocalPos1Attr().Get(),joint.GetLocalRot1Attr().Get())):
            matrix=Gf.Matrix4d(1).SetRotate(Gf.Quatd(quat));matrix.SetTranslateOnly(Gf.Vec3d(*pos))
            anchors.append(np.asarray(matrix).T.tolist())
        parent=next(name for name,path in paths.items() if path==item['body0'])
        child=next(name for name,path in paths.items() if path==item['body1'])
        joints.append({'name':item['name'],'parent':parent,'child':child,'axis':item['axis'],'parent_anchor_col':anchors[0],'child_anchor_col':anchors[1]})
    snapshot=scene.motion.snapshot(scene.native_time())
    from sensor_visualizer_v06.geometry import matrix_from_pose
    reference=matrix_from_pose(snapshot['root_position'],snapshot['root_xyzw']).T
    base=np.asarray(parts['track_link']['body_bind_world_row']).T
    manifest={'schema_version':1,'parts':parts,'joints':joints,'base_in_reference_col':(np.linalg.inv(reference)@base).tolist(),'world_frame':'world','matrix_convention':'USD row vectors; STL points are in actual rigid-body coordinates; scale and mesh alignment baked','material_policy':'diagnostic solid colors per body; original mesh geometry preserved','scene':scene.job['scene'],'scene_sha256':hashlib.sha256(Path(scene.job['scene']).read_bytes()).hexdigest()}
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

def install(output):
    from sensor_visualizer_v06.scene import SceneStepper
    from pxr import UsdGeom
    output=Path(output);original=SceneStepper.capture;asset=[None]
    async def capture(self,group,stamp):
        arrays,bundle=await original(self,group,stamp)
        if asset[0] is None:asset[0]=export_asset(self,output/'viewer_assets')
        cache=UsdGeom.XformCache()
        poses={name:np.asarray(cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath(part['body_prim']))).tolist() for name,part in asset[0]['parts'].items()}
        bundle['viewer_body_world_row']=poses
        with (output/'body_poses.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'group_id':group,'simulation_time_ns':stamp,'body_world_row':poses,'source':'actual USD rigid-body transforms after accepted frozen capture','observed_monotonic_ns':time.monotonic_ns()})+'\n')
        return arrays,bundle
    SceneStepper.capture=capture
