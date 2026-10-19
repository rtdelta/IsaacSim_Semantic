"""Independent triangle-surface checks; not a replacement RTX material simulation."""
import sys,json,collections
from pathlib import Path
import numpy as np
for b in Path('/root/isaacsim/extscache').glob('omni.warp.core-*'):
    if (b/'warp/__init__.py').exists():sys.path.insert(0,str(b));break
import warp as wp

@wp.kernel
def query(mesh:wp.uint64,points:wp.array(dtype=wp.vec3),origin:wp.vec3,
          distances:wp.array(dtype=float),faces:wp.array(dtype=int),
          ray_distances:wp.array(dtype=float),ray_faces:wp.array(dtype=int)):
    i=wp.tid();p=points[i]
    q=wp.mesh_query_point_no_sign(mesh,p,1000.0)
    distances[i]=1000.0;faces[i]=-1
    if q.result:
        hit=wp.mesh_eval_position(mesh,q.face,q.u,q.v)
        distances[i]=wp.length(hit-p);faces[i]=q.face
    direction=wp.normalize(p-origin)
    r=wp.mesh_query_ray(mesh,origin+direction*0.0001,direction,1000.0)
    ray_distances[i]=-1.0;ray_faces[i]=-1
    if r.result:
        ray_distances[i]=r.t+0.0001;ray_faces[i]=r.face

def evaluate(mesh,points,origin):
    n=len(points);args=[wp.empty(n,dtype=float,device='cuda:0'),wp.empty(n,dtype=int,device='cuda:0'),wp.empty(n,dtype=float,device='cuda:0'),wp.empty(n,dtype=int,device='cuda:0')]
    wp.launch(query,dim=n,inputs=[mesh.id,wp.array(points,dtype=wp.vec3,device='cuda:0'),wp.vec3(*origin),*args],device='cuda:0')
    return [a.numpy() for a in args]

def main():
    root=Path(sys.argv[1]);out=root/'geometry_analysis';out.mkdir(exist_ok=True)
    wp.config.kernel_cache_dir=str(out/'warp_cache');wp.init()
    # Analytical fixture verifies the transform-independent query kernel.
    fixture=wp.Mesh(points=wp.array([[-10,-10,0],[10,-10,0],[0,10,0]],dtype=wp.vec3,device='cuda:0'),indices=wp.array([0,1,2],dtype=int,device='cuda:0'))
    dist,face,rt,rf=evaluate(fixture,np.array([[0,0,0]],np.float32),[0,0,1])
    assert abs(float(dist[0]))<1e-5 and abs(float(rt[0])-1)<1e-5 and face[0]==0 and rf[0]==0
    path=root/'legacy_raw/capture/geometry';data=np.load(path/'visible_meshes.npz');manifest=json.loads((path/'manifest.json').read_text());owners=data['face_owner'];meshes=manifest['meshes']
    mesh=wp.Mesh(points=wp.array(data['vertices'],dtype=wp.vec3,device='cuda:0'),indices=wp.array(data['triangles'].reshape(-1),dtype=int,device='cuda:0'))
    rows=[]
    for family,rel in [('legacy','legacy/round_01/capture'),('native','native/round_01/capture')]:
      base=root/rel/'formal_clouds/000'
      for sid in ('MyNZ3_left','MyNZ3_right','MyNZ3_front','MyAiry_left'):
        a=np.load(base/(sid+'.npy'));meta=json.loads((base/(sid+'.json')).read_text());m=np.array(meta['world_matrix_row']);world=(a@m[:3,:3]+m[3,:3]).astype(np.float32);origin=m[3,:3];rng=np.linalg.norm(a,axis=1)
        dist,faces,raydist,rayfaces=evaluate(mesh,world,origin)
        near=rng<=2;close=dist<=0.01;valid_ray=raydist>=0
        def objects(mask):
          counts=collections.Counter(int(owners[f]) for f in faces[mask] if f>=0)
          return [{'path':meshes[k]['path'],'points':v} for k,v in counts.most_common(8)]
        rows.append({'family':family,'sensor':sid,'points':len(a),'near2':int(sum(near)),'near2_on_mesh_1cm':int(sum(near&close)),
          'near2_surface_distance_m_p50_p95_max':np.percentile(dist[near],[50,95,100]).tolist() if near.any() else None,
          'all_surface_distance_m_p50_p95_max':np.percentile(dist,[50,95,100]).tolist(),
          'near2_objects_within1cm':objects(near&close),'all_objects_within1cm':objects(close),
          'near2_first_mesh_hit_range_match_1cm':int(sum(near&valid_ray&(np.abs(raydist-rng)<=0.01))),
          'near2_closer_mesh_occludes_by_2cm':int(sum(near&valid_ray&(raydist<rng-0.02))),
          'omitted_primitives':manifest['skipped_gprims']})
        np.savez_compressed(out/(family+'_'+sid+'.npz'),world=world,local=a,ranges=rng,surface_distance=dist,surface_face=faces,first_mesh_range=raydist,first_mesh_face=rayfaces)
    report={'fixture_passed':True,'mesh_triangles':len(owners),'rows':rows,'limits':['Queries reproduce visible USD triangle geometry, not material return strength or RTX acceleration state.','Cube and Plane analytic prims omitted; nearest-surface assignment within 1cm remains direct positive evidence, absence is not proof.','Face fan triangulation used; excavator source parts are triangular, subdivision=none.','First hit queries are two sided; no opacity, material, range filter or sensor self-occlusion emulation.']}
    (out/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
