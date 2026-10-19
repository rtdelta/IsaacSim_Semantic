"""Load NZ3 in Isaac Sim 6.0 and verify actual RTX returns against analytical geometry.

Run with /root/isaacsim/python.sh isaac_demo.py. Add --gui for an interactive demo.
The default run uses a separate headless process and exits after validation.
"""
import argparse
import json
from pathlib import Path
import traceback

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gui',action='store_true')
parser.add_argument('--draw',action='store_true',help='Enable the viewport point-cloud writer, also in headless tests')
parser.add_argument('--output',type=Path,default=ROOT/'reports/isaacsim')
parser.add_argument('--max-updates',type=int,default=240)
args,kit_args=parser.parse_known_args()
args.output.mkdir(parents=True,exist_ok=True)
for old_status in ('validation.json','failure.txt'):
    (args.output/old_status).unlink(missing_ok=True)

from isaacsim import SimulationApp
app=SimulationApp(dict(headless=not args.gui,multi_gpu=False,renderer='RaytracedLighting',
                       width=960,height=720,fast_shutdown=True,
                       extra_args=['--/renderer/raytracingMotion/enabled=false',
                                   '--/rtx/hydra/supportMultiTickRate=false',
                                   '--/rtx/rendering/perSensorTickTlas=false']))
import numpy as np


def main():
    import omni.usd
    import omni.timeline
    import carb
    from pxr import UsdGeom,Sdf,Gf
    from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
    from isaac_utils import load_nz3,make_box,make_chamber,box_ranges,write_pcd
    from nz3_model import angle_error,error_stats

    omni.usd.get_context().new_stage()
    stage=omni.usd.get_context().get_stage()
    UsdGeom.SetStageMetersPerUnit(stage,1)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    stage.SetTimeCodesPerSecond(60)
    stage.DefinePrim('/World','Xform');stage.SetDefaultPrim(stage.GetPrimAtPath('/World'))
    make_chamber(stage)
    lidar,sensor=load_nz3(visualize=args.gui or args.draw)
    annot=sensor.attach_annotators('generic-model-output')['generic-model-output']
    table=np.load(ROOT/'calibration/rays.npz')
    expected_dirs=table['directions'].reshape(-1,3).astype(float)
    expected_az=table['azimuth_deg'].ravel();expected_el=table['elevation_deg'].ravel()
    total=len(expected_dirs)
    prim=stage.GetPrimAtPath('/World/NZ3/sensor')
    if len(prim.GetAttribute('omni:sensor:Core:emitterState:s001:azimuthDeg').Get())!=total:
        raise AssertionError('USD reference composition did not load all ray angles')
    print('NZ3_STAGE_READY',dict(rays=total,schema=list(prim.GetAppliedSchemas())),flush=True)
    if args.gui:
        from isaacsim.core.utils.viewports import set_camera_view
        set_camera_view(eye=np.array([-4.,-6.,3.]),target=np.array([3.,0.,0.]))
    timeline=omni.timeline.get_timeline_interface();timeline.play()

    def snapshot(settle=30):
        for _ in range(settle):app.update()
        for i in range(args.max_updates):
            app.update()
            raw=annot.get_data()
            if i in (0,30,120):
                print('NZ3_BUFFER',i,type(raw).__name__,len(raw) if raw is not None else None,
                      'timeline',timeline.get_current_time(),flush=True)
            if isinstance(raw,dict):raw=raw.get('data')
            if raw is None or len(raw)==0:continue
            gmo=parse_generic_model_output_data(raw)
            if gmo.numElements<=0:continue
            xyz=np.column_stack((gmo.x,gmo.y,gmo.z)).copy()
            ids=np.asarray(gmo.emitterId,dtype=np.int64).copy()
            result=dict(xyz=xyz,emitter_id=ids,channel_id=np.asarray(gmo.channelId).copy(),
                        frame_id=int(gmo.frameId),timestamp_ns=int(gmo.timestampNs),
                        scan_complete=int(gmo.scanComplete))
            print('NZ3_FRAME',dict(points=len(xyz),frame=result['frame_id'],complete=result['scan_complete'],
                                  coords_type=str(gmo.elementsCoordsType),first_points=xyz[:2].tolist(),
                                  id_range=[int(ids.min()),int(ids.max())]),flush=True)
            if len(xyz)==total:return result
        raise RuntimeError('No complete 46,080-point scan received in the enclosed chamber')

    def verify(frame,expected_range,name):
        ids=frame['emitter_id'];xyz=frame['xyz'].astype(float)
        if len(np.unique(ids))!=total or ids.min()!=0 or ids.max()!=total-1:
            raise AssertionError('RTX emitter IDs must cover all 46,080 samples exactly once')
        order=np.argsort(ids);xyz=xyz[order]
        dist=np.linalg.norm(xyz,axis=1)
        az=np.degrees(np.arctan2(xyz[:,1],xyz[:,0]))
        el=np.degrees(np.arctan2(xyz[:,2],np.hypot(xyz[:,0],xyz[:,1])))
        angular=angle_error(az,el,expected_az,expected_el)
        distance_error=np.abs(dist-expected_range)
        result=dict(points=len(xyz),unique_emitters=len(np.unique(ids)),
                    angular_error=error_stats(angular),range_error_max_m=float(distance_error.max()),
                    range_error_p95_m=float(np.quantile(distance_error,.95)),
                    azimuth_deg=[float(az.min()),float(az.max())],elevation_deg=[float(el.min()),float(el.max())],
                    frame_id=frame['frame_id'],scan_complete=frame['scan_complete'])
        print('NZ3_CHECK',name,json.dumps(result),flush=True)
        np.savez_compressed(args.output/f'{name}_points.npz',xyz=xyz,emitter_id=np.arange(total),
                            ring=table['ring'].ravel(),column=table['column'].ravel(),source=table['source'].ravel(),
                            expected_range_m=expected_range,observed_range_m=dist)
        write_pcd(args.output/f'{name}.pcd',xyz,table['ring'].ravel())
        if angular.max()>.005:raise AssertionError(f'{name}: rendered angles differ from calibration')
        if distance_error.max()>.02:raise AssertionError(f'{name}: RTX ranges differ from analytical ray-box intersections')
        return result,dist

    chamber_expected=box_ranges(expected_dirs,[-10]*3,[10]*3)
    chamber,base_dist=verify(snapshot(),chamber_expected,'chamber')
    make_box(stage,'/World/test_target',(5,0,0),(1,2,2),(.95,.25,.1))
    target_expected=np.minimum(chamber_expected,box_ranges(expected_dirs,[4.5,-1,-1],[5.5,1,1]))
    target,target_dist=verify(snapshot(settle=40),target_expected,'with_target')
    changed=int((np.abs(base_dist-target_dist)>.1).sum())
    if changed<100:raise AssertionError('Adding the test target must change the simulated point cloud')
    stage.Flatten().Export(str(args.output/'verified_scene.usda'))
    result=dict(passed=True,version_file=(Path('/root/isaacsim/VERSION').read_text().strip() if Path('/root/isaacsim/VERSION').exists() else 'see run log'),
                asset=str(ROOT/'assets/NZ3/NZ3.usda'),chamber=chamber,with_target=target,
                changed_ranges_after_adding_target=changed,
                scope='GPU-rendered static geometry and angle-table equivalence; no device noise/intensity/timing equivalence claimed.')
    (args.output/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('NZ3_RENDER_VALIDATION_PASSED',json.dumps(result),flush=True)
    if args.gui:
        while app.is_running():app.update()
    timeline.stop()


exit_code=0
try:
    main()
except Exception:
    exit_code=1
    error=traceback.format_exc();print(error,flush=True)
    (args.output/'failure.txt').write_text(error,encoding='utf-8')
finally:
    app.close(wait_for_replicator=False,exit_code=exit_code)
raise SystemExit(exit_code)
