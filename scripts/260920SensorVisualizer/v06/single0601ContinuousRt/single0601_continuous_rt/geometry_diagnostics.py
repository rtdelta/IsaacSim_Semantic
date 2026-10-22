"""Anonymous diagnostic surface and markers; no disk USD or formal sensor model edits."""
import io
import math
import numpy as np
from .common import save_json,ContractError
from .geometry import OPTICAL_TO_USD


def create(owner,directory):
    from pxr import Usd,UsdGeom,Gf
    o=owner
    camera=next((c for c in o.registry['cameras'] if c['id']=='front'),None)
    if camera is None:
        raise ContractError('geometry_selection','Known marker diagnostic requires the front camera')
    state=o.ledger.exact_time(o.epoch_id,round(o.manager.get_simulation_time()*1e9))[1]
    optical=OPTICAL_TO_USD@np.asarray(state['sensor_world_matrices_usd'][camera['sensor_id']])
    def cube(name,center,halfsize,color):
        transform=np.eye(4)
        transform[:3,:3]=np.diag(halfsize)
        transform[3,:3]=center
        world=transform@optical
        path='/Single0601ContinuousRtDiagnostics/'+name
        with Usd.EditContext(o.stage,o.layer):
            prim=UsdGeom.Cube.Define(o.stage,path)
            prim.CreateSizeAttr(2.)
            prim.AddTransformOp().Set(Gf.Matrix4d(world.tolist()))
            prim.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        return {'prim_path':path,'world_matrix_usd':world.tolist(),'halfsize_local_m':halfsize,'display_color':color}
    board=cube('KnownPlane',[0.,0.,15.],[15.,15.,.001],[.8,.8,.8])
    markers=[]
    for name,x,y,color in [('red',-5.,-3.,[1.,0.,0.]),('green',-3.5,-4.,[0.,1.,0.]),('blue',-2.,-3.,[0.,0.,1.])]:
        marker=cube('Marker_'+name,[x,y,14.997],[.12,.12,.001],color)
        marker.update(color_name=name,world_center_m=(np.array([x,y,14.996,1.])@optical)[:3].tolist(),
            world_feature_corners_m=[(np.array([x+dx,y+dy,14.996,1.])@optical)[:3].tolist() for dx,dy in ((-.12,-.12),(.12,-.12),(.12,.12),(-.12,.12))])
        markers.append(marker)
    noise_overrides=[]
    if o.job.get('diagnostics',{}).get('noiseless_plane'):
        from .sensor_registry import attributes
        for lidar in o.registry['lidars']:
            prim=o.stage.GetPrimAtPath(lidar['prim_path'])
            attr=prim.GetAttribute('omni:sensor:Core:rangeAccuracyM')
            if not attr or attr.Get() is None:
                raise ContractError('diagnostic_noise','Installed sensor has no rangeAccuracyM field')
            before=float(attr.Get())
            with Usd.EditContext(o.stage,o.layer):attr.Set(0.)
            override={'prim_path':lidar['prim_path'],'attribute':attr.GetName(),'before':before,'after':float(attr.Get()),
                      'usd_type':str(attr.GetTypeName()),'unit':'m; installed generatedSchema.usda userDocBrief',
                      'scope':'explicit anonymous noiseless-plane diagnostic only'}
            noise_overrides.append(override)
            o.sensor_overrides.append(override)
            lidar['parameters']=attributes(prim)
    spec={'schema_version':1,'scope':'anonymous known surface diagnostic, distinct from scene18 quality comparison',
          'camera_id':camera['id'],'optical_reference_world_usd':optical.tolist(),'board':board,'markers':markers,
          'plane_local_z_m':14.999,'plane_roi_halfsize_m':14.,'normal_selection_halfwidth_m':.5,
          'reprojection_p95_threshold_px':1.,'point_plane_p95_threshold_m':.005,
          'motion':o.job.get('diagnostics',{}).get('geometry_motion',{'speed_m_s':3.,'yaw_rate_deg_s':10.}),
          'native_sensor_noise':'explicit diagnostic zero range accuracy' if noise_overrides else 'unchanged; failures cannot be hidden by filtering noise',
          'noise_overrides':noise_overrides,'feature_extractor':'color-connected components with known projected area, aspect and solidity; ambiguous/missing markers excluded with evidence',
          'exposure_model':'instantaneous, motion blur disabled'}
    save_json(directory/'diagnostic_geometry.json',spec)
    return spec


def project(world,usd_to_world,calibration):
    optical=OPTICAL_TO_USD@np.asarray(usd_to_world)
    point=np.r_[world,1.]@np.linalg.inv(optical)
    x,y,z=point[:3]
    if z<=0:
        return None
    radius=math.hypot(x,y)
    theta=math.atan2(radius,z)
    k=calibration['intrinsics']
    distorted=theta*(1+k['k1']*theta**2+k['k2']*theta**4+k['k3']*theta**6+k['k4']*theta**8)
    scale=distorted/radius if radius>1e-12 else 1/z
    return np.array([k['fx']*x*scale+k['cx'],k['fy']*y*scale+k['cy']])


def measure(frame,decoded,registry,spec):
    from PIL import Image
    camera=next(c for c in registry['cameras'] if c['id']==spec['camera_id'])
    msg=decoded[camera['topic_prefix']+'/image_raw/compressed']
    with Image.open(io.BytesIO(bytes(msg.data))) as image:
        pixels=np.array(image,dtype=float)
    reprojection=[]
    rejected=[]
    for marker in spec['markers']:
        predicted=project(marker['world_center_m'],frame['state']['sensor_world_matrices_usd'][camera['sensor_id']],camera['calibration'])
        if predicted is None:
            continue
        x,y=predicted
        if not 35<=x<pixels.shape[1]-35 or not 35<=y<pixels.shape[0]-35:
            continue
        left,right,top,bottom=int(x)-30,int(x)+31,int(y)-30,int(y)+31
        region=pixels[top:bottom,left:right]
        channel={'red':0,'green':1,'blue':2}[marker['color_name']]
        others=[n for n in range(3) if n!=channel]
        # Use color dominance under either bright or shaded illumination. This
        # affects feature detection only; the 1px acceptance bound is unchanged.
        mask=(region[:,:,channel]>10)&(region[:,:,channel]>1.8*region[:,:,others[0]])&(region[:,:,channel]>1.8*region[:,:,others[1]])
        corners=marker.get('world_feature_corners_m')
        if corners is None:
            inverse_ref=np.linalg.inv(np.asarray(spec['optical_reference_world_usd']))
            center=np.r_[marker['world_center_m'],1.]@inverse_ref
            corners=[(np.array([center[0]+dx,center[1]+dy,center[2],1.])@np.asarray(spec['optical_reference_world_usd']))[:3].tolist() for dx,dy in ((-.12,-.12),(.12,-.12),(.12,.12),(-.12,.12))]
        polygon=[project(w,frame['state']['sensor_world_matrices_usd'][camera['sensor_id']],camera['calibration']) for w in corners]
        if any(p is None for p in polygon):continue
        polygon=np.array(polygon)
        area=abs(np.dot(polygon[:,0],np.roll(polygon[:,1],1))-np.dot(polygon[:,1],np.roll(polygon[:,0],1)))/2
        components=connected_components(mask)
        candidates=[]
        for yy,xx in components:
            width,height=int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)
            n=len(xx)
            if n>=4 and .7*area<=n<=1.6*area and max(width,height)<=3*min(width,height) and n/(width*height)>=.6:
                candidates.append((yy,xx))
        if len(candidates)!=1:
            rejected.append({'marker':marker['color_name'],'reason':'no unique isolated marker component','valid_components':len(candidates),'projected_area_px':float(area)})
            continue
        yy,xx=candidates[0]
        measured=np.array([float(np.mean(xx))+left,float(np.mean(yy))+top])
        reprojection.append({'marker':marker['color_name'],'predicted_xy_px':predicted.tolist(),'measured_xy_px':measured.tolist(),
                             'error_px':float(np.linalg.norm(predicted-measured)),'feature_pixels':len(xx)})
    inverse=np.linalg.inv(np.asarray(spec['optical_reference_world_usd']))
    planes=[]
    for lidar in registry['lidars']:
        raw=bytes(decoded[lidar['topic']].data)
        local=np.frombuffer(raw,dtype='<f4').reshape(-1,3)
        world=np.c_[local,np.ones(len(local))]@np.asarray(frame['state']['sensor_world_matrices_usd'][lidar['sensor_id']])
        reference=world@inverse
        error=np.abs(reference[:,2]-spec['plane_local_z_m'])
        mask=(np.abs(reference[:,0])<spec['plane_roi_halfsize_m'])&(np.abs(reference[:,1])<spec['plane_roi_halfsize_m'])&(error<spec['normal_selection_halfwidth_m'])
        selected=error[mask]
        planes.append({'sensor_id':lidar['sensor_id'],'surface_points':len(selected),
                       'point_plane_p95_m':float(np.quantile(selected,.95,method='higher')) if len(selected)>=100 else None,
                       'max_m':float(selected.max()) if len(selected) else None})
    return {'group_id':frame['group_id'],'target_step':frame['target_step'],'reprojection':reprojection,'rejected_features':rejected,'planes':planes}


def connected_components(mask):
    """Four-connected pixels; no predictor-based choice of a feature centroid."""
    visited=np.zeros(mask.shape,dtype=bool)
    result=[]
    for row,col in zip(*np.nonzero(mask)):
        if visited[row,col]:continue
        stack=[(row,col)]
        visited[row,col]=True
        rows,cols=[],[]
        while stack:
            y,x=stack.pop()
            rows.append(y);cols.append(x)
            for yy,xx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                if 0<=yy<mask.shape[0] and 0<=xx<mask.shape[1] and mask[yy,xx] and not visited[yy,xx]:
                    visited[yy,xx]=True
                    stack.append((yy,xx))
        result.append((np.array(rows),np.array(cols)))
    return result
