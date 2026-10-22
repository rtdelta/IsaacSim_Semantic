"""Helpers imported after Isaac Sim starts. No ROS or bag-reader dependency."""
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
_checker_handle = None


def validate_nz3_profile():
    """Fail early on renderer parameters; retain the dynamically loaded checker."""
    global _checker_handle
    import isaacsim.sensors.experimental.rtx.sensor_checker as sc
    info=sc.ModelInfo()
    info.modelName='lidar.core';info.modelVendor='nv'
    info.modelVersion='1.0';info.schemaVersion='1.0'
    checker=sc.SensorCheckerUtil()
    directory=Path(sc.__file__).parent
    candidates=list(directory.glob('*rtx.sensors.lidar.core.nv.chk.impl.*'))
    error=checker.init(info,str(candidates[0]) if candidates else None)
    if error:raise RuntimeError(f'NZ3 sensor checker library: {error}')
    error=checker.validateParams(str(ROOT/'assets/NZ3/config/NZ3_scan.usda'),'/OmniLidar')
    if error:raise ValueError(f'NZ3 renderer profile: {error}')
    _checker_handle=checker


def load_nz3(prim_path='/World/NZ3', position=(0,0,0), yaw_deg=0, visualize=False):
    """Reference the portable asset into the current stage; keep returned sensor alive.

    May be used from Isaac Sim's Script Editor with this folder on sys.path.
    Does not clear the current stage or change any existing prim.
    """
    import omni.usd
    from pxr import UsdGeom, Gf
    from isaacsim.sensors.experimental.rtx import Lidar, LidarSensor
    validate_nz3_profile()
    stage=omni.usd.get_context().get_stage()
    if stage.GetPrimAtPath(prim_path).IsValid():
        raise ValueError(f'Choose a fresh prim path: {prim_path} already exists')
    prim=stage.DefinePrim(prim_path,'Xform')
    prim.GetReferences().AddReference(str(ROOT/'assets/NZ3/MyNZ3.usda'))
    xf=UsdGeom.Xformable(prim)
    xf.AddTranslateOp().Set(Gf.Vec3d(*position))
    xf.AddRotateZOp().Set(float(yaw_deg))
    lidar=Lidar(prim_path+'/sensor',aux_output_level='BASIC',tick_rate=10,
                accumulate_outputs=True,reset_xform_op_properties=False)
    if visualize:
        from isaacsim.core.experimental.utils.app import enable_extension
        enable_extension('isaacsim.sensors.rtx.nodes')
    # LidarSensor snapshots the writer registry on construction.
    sensor=LidarSensor(lidar,annotators=[])
    if visualize:
        sensor.attach_writer('draw-point-cloud',size=.018,color=[.1,1,.65,1])
    return lidar,sensor


def make_box(stage,path,center,size,color=(.55,.6,.65)):
    from pxr import UsdGeom,Gf
    box=UsdGeom.Cube.Define(stage,path)
    box.CreateSizeAttr(1)
    box.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    box.AddTranslateOp().Set(Gf.Vec3d(*center))
    box.AddScaleOp().Set(Gf.Vec3d(*size))
    return box


def make_chamber(stage,half_extent=10.0):
    """Six solid walls: first intersection is exactly a centred +/-10 m box."""
    for axis in range(3):
        for sign in (-1,1):
            center=[0.,0.,0.];center[axis]=sign*(half_extent+.1)
            size=[2*half_extent+.4]*3;size[axis]=.2
            make_box(stage,f'/World/chamber/wall_{axis}_{sign+1}',center,size)


def box_ranges(unit_directions,lower,upper):
    """Slab intersection, returning +inf for a miss; handles zero components."""
    d=np.asarray(unit_directions,dtype=float)
    lower=np.asarray(lower,dtype=float);upper=np.asarray(upper,dtype=float)
    parallel=np.abs(d)<1e-12
    safe=np.where(parallel,1.,d)
    t1,t2=lower/safe,upper/safe
    near=np.where(parallel,-np.inf,np.minimum(t1,t2))
    far=np.where(parallel,np.inf,np.maximum(t1,t2))
    outside=(parallel&((lower>0)|(upper<0))).any(axis=1)
    entry,leave=near.max(axis=1),far.min(axis=1)
    hit=(~outside)&(leave>=np.maximum(entry,0))
    return np.where(hit,np.where(entry>0,entry,leave),np.inf)


def write_pcd(path,xyz,ring):
    data=np.empty(len(xyz),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('ring','<u2')])
    for i,k in enumerate(('x','y','z')):data[k]=xyz[:,i]
    data['ring']=ring
    header=f'# .PCD v0.7\nVERSION 0.7\nFIELDS x y z ring\nSIZE 4 4 4 2\nTYPE F F F U\nCOUNT 1 1 1 1\nWIDTH {len(data)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(data)}\nDATA binary\n'
    with Path(path).open('wb') as stream:
        stream.write(header.encode('ascii'));stream.write(data.tobytes())
