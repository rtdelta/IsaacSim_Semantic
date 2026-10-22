"""Isolated runtime smoke test of the assembled scene; edits stay in Session."""
import argparse
import json
from pathlib import Path
import traceback
import faulthandler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'reports/combine_stage'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT/'runtime.json'
REPORT.write_text(json.dumps({'passed': False, 'status': 'starting'}))
faulthandler.enable()
faulthandler.dump_traceback_later(180, repeat=True)
parser = argparse.ArgumentParser()
parser.add_argument('--scene', default=json.loads((ROOT/'config/combine_stage.json').read_text())['output_scene'])
args, _ = parser.parse_known_args()

from isaacsim import SimulationApp
app = SimulationApp(dict(headless=True, multi_gpu=False, fast_shutdown=True,
    renderer='RaytracedLighting', width=1280, height=800,
    extra_args=['--/renderer/raytracingMotion/enabled=false',
                '--/rtx/hydra/supportMultiTickRate=false',
                '--/rtx/rendering/perSensorTickTlas=false']))
import numpy as np
import omni.usd
import omni.timeline
import omni.physx
import omni.replicator.core as rep
from pxr import Usd, UsdGeom, UsdPhysics, Sdf
from PIL import Image
from isaacsim.core.experimental.prims import Articulation
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
from contract_math import forward, load_config, sha256, write_json

report = {'passed': False, 'scene': args.scene, 'scene_sha256': sha256(args.scene),
          'scope': 'Native articulation, all sensor mounting frames, RGB, 13 RTX GMO outputs. No ROS/MCAP pipeline.',
          'poses': [], 'lidars': {}}
timeline = omni.timeline.get_timeline_interface()
products, annots = [], []
try:
    print('COMBINE_OPEN_START', args.scene, flush=True)
    assert omni.usd.get_context().open_stage(args.scene)
    print('COMBINE_OPEN_DONE', flush=True)
    for _ in range(12): app.update()
    print('COMBINE_WARMUP_DONE', flush=True)
    stage = omni.usd.get_context().get_stage()
    report['composition_errors'] = [str(e) for e in stage.GetCompositionErrors()]
    assert not report['composition_errors'], report['composition_errors']
    assert stage.GetPrimAtPath('/FlatGrid/Environment'), 'Inherited NVIDIA grid did not load'
    stage.SetEditTarget(stage.GetSessionLayer())
    # Test products are separate from saved products and do not change the scene.
    stage.GetPrimAtPath('/World/Stage10SensorPipeline').SetActive(False)
    for p in stage.GetPrimAtPath('/Render/Products').GetChildren(): p.SetActive(False)
    stage.GetPrimAtPath('/Render/Settings').GetRelationship('products').SetTargets([])
    cfg = load_config(); root = '/World/Excavator'
    manifest = json.loads((OUT/'build.json').read_text())
    assert manifest['scene_sha256'] == report['scene_sha256'], 'Scene differs from verified build'
    for j in cfg['joints']:
        drive = UsdPhysics.DriveAPI(stage.GetPrimAtPath(root+'/Joints/'+j['name']), 'angular')
        drive.CreateStiffnessAttr(0); drive.CreateDampingAttr(0); drive.CreateMaxForceAttr(0)
    art = Articulation(root+'/track_link', reset_xform_op_properties=False)
    print('COMBINE_ATTACH_START', flush=True)
    rgb_product = rep.create.render_product('/World/ContractOverview', (1280,800), name='ContractCheckRGB')
    rgb = rep.AnnotatorRegistry.get_annotator('rgb', device='cpu')
    rgb.attach([rgb_product.path]); products.append(rgb_product); annots.append(rgb)
    runtimes = []
    for row in manifest['sensors']:
        if row['type'] != 'OmniLidar': continue
        sensor = stage.GetPrimAtPath(row['sensor'])
        sensor.CreateAttribute('omni:sensor:Core:elementsCoordsType', Sdf.ValueTypeNames.Token).Set('CARTESIAN')
        sensor.CreateAttribute('omni:sensor:Core:outputFrameOfReference', Sdf.ValueTypeNames.Token).Set('SENSOR')
        sensor.CreateAttribute('_replicator:rendervar:GenericModelOutput:channels', Sdf.ValueTypeNames.StringArray).Set(['BASIC'])
        product = rep.create.render_product(row['sensor'], (1,1), name='ContractCheck'+row['name'], render_vars=['GenericModelOutput'])
        annot = rep.AnnotatorRegistry.get_annotator('GenericModelOutput', device='cpu', do_array_copy=True)
        annot.attach([product.path]); products.append(product); annots.append(annot)
        runtimes.append((row, annot))
        report['lidars'][row['name']] = {'fresh_frames': [], 'point_counts': []}
    timeline.play()
    print('COMBINE_PLAY', flush=True)
    for _ in range(120):
        app.update()
        if art.is_physics_tensor_entity_valid(): break
    assert art.is_physics_tensor_entity_valid()
    assert art.num_dofs == 4
    names = [j['name'] for j in cfg['joints']]
    indices = art.get_dof_indices(names).numpy().astype(int).ravel().tolist()
    report['dof_indices'] = dict(zip(names, indices))
    base = np.asarray(manifest['base_world_matrix'])
    def world(path):
        return np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(stage.GetPrimAtPath(path))).T
    def apply(q):
        values = np.zeros((1, art.num_dofs), dtype=np.float32)
        for n, i in zip(names, indices): values[0,i] = np.deg2rad(q.get(n, 0))
        art.set_dof_positions(values); art.set_dof_velocities(np.zeros_like(values))
        SimulationManager.get_physics_simulation_view().update_articulations_kinematic()
        omni.physx.get_physx_interface().update_transformations(False, True, False, False)
    for label, q in [('bind', {}), ('combined', {'swing':15, 'boom':10, 'arm':-15, 'bucket':15})]:
        apply(q); frames = forward(cfg, q)
        row = {'name': label, 'degrees': q, 'sensor_position_errors_m': {}, 'body_position_errors_m': {}}
        for part in cfg['parts']:
            expected = base @ frames[part['frame']]
            actual = world(root+'/'+part['frame'])
            error = float(np.linalg.norm(actual[:3,3]-expected[:3,3]))
            assert error < 5e-5 and np.max(np.abs(actual[:3,:3]-expected[:3,:3])) < 1e-5, (part['id'], error)
            row['body_position_errors_m'][part['frame']] = error
        for mount in manifest['sensors']:
            expected = base @ frames[mount['parent_frame']] @ np.asarray(mount['parent_from_mount'])
            actual = world(mount['mount'])
            error = float(np.linalg.norm(actual[:3,3]-expected[:3,3]))
            assert error < 5e-5 and np.max(np.abs(actual[:3,:3]-expected[:3,:3])) < 1e-5, (mount['name'], error)
            row['sensor_position_errors_m'][mount['name']] = error
        report['poses'].append(row)
        for _ in range(24): apply(q); app.update()
        image = np.asarray(rgb.get_data())
        assert image.shape[:2] == (800,1280) and float(image[...,:3].std()) > 3
        Image.fromarray(image.astype(np.uint8)).save(OUT/(label+'_scene.png'))
        print('COMBINE_POSE_OK', label, flush=True)
    apply({})
    for step in range(100):
        apply({}); app.update()
        for row, annot in runtimes:
            raw = annot.get_data()
            if isinstance(raw, dict): raw = raw.get('data')
            if raw is None or not len(raw): continue
            g = parse_generic_model_output_data(raw)
            if not g.scanComplete or not g.numElements: continue
            stat = report['lidars'][row['name']]
            frame = int(g.frameId)
            if frame in stat['fresh_frames']: continue
            xyz = np.column_stack([g.x,g.y,g.z])
            assert np.isfinite(xyz).all(), row['name']
            nonzero = int(np.count_nonzero(np.linalg.norm(xyz,axis=1)>0))
            assert nonzero > 0, row['name']
            stat['fresh_frames'].append(frame); stat['point_counts'].append(nonzero)
        if all(len(st['fresh_frames']) >= 2 for st in report['lidars'].values()): break
    assert all(len(st['fresh_frames']) >= 2 for st in report['lidars'].values()), report['lidars']
    assert sha256(args.scene) == report['scene_sha256'], 'Runtime altered the saved scene'
    report.update(passed=True, status='complete')
    print('COMBINE_RUNTIME_OK', json.dumps(report['lidars']), flush=True)
except Exception:
    report.update(status='failed', error=traceback.format_exc())
    print(report['error'], flush=True)
finally:
    write_json(REPORT, report)
    faulthandler.cancel_dump_traceback_later()
    timeline.stop()
    for annot, product in zip(annots, products):
        try: annot.detach([product.path]); product.destroy()
        except Exception: pass
    app.close()
