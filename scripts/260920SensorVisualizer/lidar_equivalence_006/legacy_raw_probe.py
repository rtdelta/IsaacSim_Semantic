"""Optional isolated raw observer. Not installed for baseline cases."""
import json,traceback
from pathlib import Path
import numpy as np

def export_geometry(stage,out):
    from pxr import UsdGeom
    cache=UsdGeom.XformCache();vertices=[];triangles=[];face_owner=[];rows=[];skipped=[];offset=0
    for p in stage.Traverse():
        if not p.IsA(UsdGeom.Gprim):continue
        visible=UsdGeom.Imageable(p).ComputeVisibility()!='invisible'
        if not p.IsA(UsdGeom.Mesh):
            skipped.append({'path':str(p.GetPath()),'type':p.GetTypeName(),'visible':visible});continue
        if not visible:continue
        g=UsdGeom.Mesh(p);pts=np.asarray(g.GetPointsAttr().Get(),dtype=np.float64)
        matrix=np.asarray(cache.GetLocalToWorldTransform(p));world=pts@matrix[:3,:3]+matrix[3,:3]
        counts=np.asarray(g.GetFaceVertexCountsAttr().Get(),dtype=np.int64);indices=np.asarray(g.GetFaceVertexIndicesAttr().Get(),dtype=np.int64)
        holes=set(g.GetHoleIndicesAttr().Get() or []);faces=[];cursor=0
        for fi,n in enumerate(counts):
            face=indices[cursor:cursor+n];cursor+=n
            if fi in holes:continue
            for j in range(1,n-1):faces.append([face[0]+offset,face[j]+offset,face[j+1]+offset])
        face_owner.extend([len(rows)]*len(faces));vertices.append(world.astype(np.float32));triangles.extend(faces)
        rows.append({'path':str(p.GetPath()),'vertices':len(pts),'triangles':len(faces),'nontriangular_faces':int(np.count_nonzero(counts!=3)),'subdivision':str(g.GetSubdivisionSchemeAttr().Get()),'double_sided':g.GetDoubleSidedAttr().Get(),'orientation':str(g.GetOrientationAttr().Get()),'matrix_row':matrix.tolist()});offset+=len(pts)
    out=Path(out)/'geometry';out.mkdir(exist_ok=True)
    np.savez_compressed(out/'visible_meshes.npz',vertices=np.concatenate(vertices),triangles=np.asarray(triangles,np.int32),face_owner=np.asarray(face_owner,np.int32))
    (out/'manifest.json').write_text(json.dumps({'meshes':rows,'skipped_gprims':skipped,'method':'Visible USD Mesh world-space triangles; fan triangulation; no material, alpha, displacement or RTX BVH emulation'},indent=2))

def install(out):
    from sensor_visualizer_v06.sensors import SensorDrivers
    from sensor_visualizer_v06.scene import SceneStepper
    initialize=SensorDrivers._initialize;capture=SceneStepper.capture
    async def initialize_raw(self,*args,**kwargs):
        await initialize(self,*args,**kwargs)
        self.nc006_raw={}
        for entry,product in zip([e for k in ('cameras','lidars') for e in self.registry[k]],self.products):
            if ('lidars',entry['id']) not in self.readers:continue
            anns=[]
            for name in ('GenericModelOutput','StableIdMap'):
                ann=self.rep.AnnotatorRegistry.get_annotator(name,device='cpu',do_array_copy=True)
                ann.attach([product.path]);anns.append(ann)
            # A Writer owns its attached annotator node; its prototype does not
            # gain _node_path. Attach an explicit observer to that same template.
            reader=self.rep.AnnotatorRegistry.get_annotator('IsaacExtractRTXSensorPointCloud',device='cpu',do_array_copy=False)
            reader.attach([product.path])
            self.nc006_raw[entry['id']]=(product.path,*anns,reader)
    async def capture_raw(self,group,stamp_ns):
        arrays,bundle=await capture(self,group,stamp_ns)
        from dual_observe import compare_exits
        for sid,(product,raw,ids,ann) in self.drivers.nc006_raw.items():
            try:compare_exits(out,group,sid,ann,ann,arrays['lidar/'+sid],self.stage,product,stamp_ns/1e9,raw,ids)
            except Exception:
                with (Path(out)/'raw_probe_errors.jsonl').open('a') as f:f.write(json.dumps({'group':group,'sensor':sid,'traceback':traceback.format_exc()})+'\n')
        if group==0:export_geometry(self.stage,out)
        return arrays,bundle
    SensorDrivers._initialize=initialize_raw;SceneStepper.capture=capture_raw
