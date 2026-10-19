"""Isolated Isaac process: native articulation/FK checks and RGB previews."""
import argparse
import json
from pathlib import Path
import traceback

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path)
args,_=parser.parse_known_args()
config=json.loads((ROOT/'config/assembly.json').read_text())
bundle=args.bundle or ROOT/'assets'/config['asset_name']
report_file=ROOT/'reports/isaac_validation.json'
report_file.write_text(json.dumps({'passed':False,'status':'starting'}))

from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'multi_gpu':False,'fast_shutdown':True,
    'renderer':'RaytracedLighting','width':1280,'height':800,
    'extra_args':['--/renderer/raytracingMotion/enabled=false',
                  '--/rtx/hydra/supportMultiTickRate=false',
                  '--/rtx/rendering/perSensorTickTlas=false']})
import numpy as np
import omni.usd
import omni.timeline
import omni.physx
import omni.replicator.core as rep
from pxr import Usd, UsdGeom, UsdPhysics
from isaacsim.core.experimental.prims import Articulation
from isaacsim.core.simulation_manager import SimulationManager
from PIL import Image
from contract_math import forward, sha256, write_json, points

report={'passed':False,'asset_manifest_sha256':sha256(bundle/'manifest.json'),
        'cases':[],'source_asset_sha256':sha256(bundle/(config['asset_name']+'.usda')),
        'scope':'Native 4-DOF articulation, zero/positive/negative/combined FK and RGB rendering. No ROS or LiDAR recording.'}
timeline=omni.timeline.get_timeline_interface()
try:
    assert omni.usd.get_context().open_stage(str(bundle/(config['asset_name']+'_preview.usda')))
    for _ in range(12):app.update()
    stage=omni.usd.get_context().get_stage()
    # All test poses and drive overrides live in the anonymous session layer.
    stage.SetEditTarget(stage.GetSessionLayer())
    for j in config['joints']:
        drive=UsdPhysics.DriveAPI(stage.GetPrimAtPath('/World/Excavator/Joints/'+j['name']),'angular')
        drive.CreateStiffnessAttr(0);drive.CreateDampingAttr(0);drive.CreateMaxForceAttr(0)
    art=Articulation('/World/Excavator/track_link',reset_xform_op_properties=False)
    product=rep.create.render_product('/World/Camera',(1280,800),name='ContractPreview')
    rgb=rep.AnnotatorRegistry.get_annotator('rgb',device='cpu');rgb.attach([product.path])
    timeline.play()
    for _ in range(120):
        app.update()
        if art.is_physics_tensor_entity_valid():break
    assert art.is_physics_tensor_entity_valid(),'Articulation failed to initialize'
    names=[j['name'] for j in config['joints']]
    indices=art.get_dof_indices(names).numpy().astype(int).ravel().tolist()
    assert art.num_dofs==4,(art.num_dofs,indices)
    report['dof_indices']=dict(zip(names,indices));report['links']=art.link_names
    base=np.array(UsdGeom.Xformable(stage.GetPrimAtPath('/World/Excavator')).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
    cases=[('bind',{})]
    for name in names:
        cases.extend([(name+'_positive',{name:15}),(name+'_negative',{name:-15})])
    cases.append(('combined',{'swing':15,'boom':10,'arm':-15,'bucket':15}))
    # Independent ordered pin coordinates for the native articulation comparisons.
    sampled_raw={}
    for part in config['parts']:
        prim=stage.GetPrimAtPath('/World/Excavator/'+part['frame']+'/Visuals/Splat')
        xyz=np.asarray(prim.GetAttribute('positions').Get())
        sampled_raw[part['frame']]=xyz[np.linspace(0,len(xyz)-1,512,dtype=int)].copy()
    bind_frames=forward(config)
    manifest=json.loads((bundle/'manifest.json').read_text())
    common=np.array(manifest['raw_to_base'])
    def apply(q):
        values=np.zeros((1,art.num_dofs),dtype=np.float32)
        for n,i in zip(names,indices):values[0,i]=np.deg2rad(q.get(n,0))
        art.set_dof_positions(values)
        art.set_dof_velocities(np.zeros_like(values))
        SimulationManager.get_physics_simulation_view().update_articulations_kinematic()
        omni.physx.get_physx_interface().update_transformations(False,True,False,False)
    for label,q in cases:
        apply(q)
        expected=forward(config,q)
        row={'name':label,'command_degrees':q,'parts':{}}
        measured=art.get_dof_positions().numpy()[0]
        row['dof_angle_max_error_rad']=max(abs(float(measured[i])-np.deg2rad(q.get(n,0))) for n,i in zip(names,indices))
        assert row['dof_angle_max_error_rad']<1e-6
        for part in config['parts']:
            frame=part['frame'];prim=stage.GetPrimAtPath('/World/Excavator/'+frame)
            actual=np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
            target=base @ expected[frame]
            position_error=float(np.linalg.norm(actual[:3,3]-target[:3,3]))
            rotation_error=float(np.max(np.abs(actual[:3,:3]-target[:3,:3])))
            visual=stage.GetPrimAtPath(str(prim.GetPath())+'/Visuals')
            model=np.array(UsdGeom.Xformable(visual).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).T
            counterpart=base @ expected[frame] @ np.linalg.inv(bind_frames[frame]) @ common
            error=float(np.max(np.linalg.norm(points(model,sampled_raw[frame])-points(counterpart,sampled_raw[frame]),axis=1)))
            row['parts'][frame]={'position_error_m':position_error,'rotation_matrix_error':rotation_error,'sampled_gaussian_center_error_m':error}
            assert position_error<3e-5,(label,frame,'position',position_error)
            assert rotation_error<3e-6,(label,frame,'rotation',rotation_error)
            assert error<5e-5,(label,frame,'geometry',error)
        report['cases'].append(row);write_json(report_file,report)
        print('NATIVE_POSE_OK',label,flush=True)
        if label in ('bind','combined'):
            for _ in range(24):apply(q);app.update()
            image=np.asarray(rgb.get_data())
            assert image.shape[:2]==(800,1280),image.shape
            assert float(image[...,:3].std())>3,'Blank RGB preview'
            Image.fromarray(image.astype(np.uint8)).save(ROOT/'reports'/(label+'_preview.png'))
    apply({})
    assert sha256(bundle/(config['asset_name']+'.usda'))==report['source_asset_sha256'],'Asset changed during validation'
    report.update(passed=True,status='complete',case_count=len(cases))
except Exception:
    report.update(error=traceback.format_exc(),status='failed')
    print(report['error'],flush=True)
finally:
    write_json(report_file,report)
    timeline.stop()
    app.close()
