"""Native Kit/PhysX/ROS TF QA on a geometry-free copy of the actual robot frames."""
import asyncio
import json
from pathlib import Path
import sys
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validation/results/origin03_horizontal'
sys.path.insert(0, str(ROOT))
import carb
import omni.kit.app
import omni.usd
import omni.physx
from pxr import Gf, Sdf, Usd, UsdGeom
from lidar_visualizer.config import load_config
from lidar_visualizer.robot_discovery import discover_robots, bind_config
from lidar_visualizer.articulation_motion import ArticulationMotion
from lidar_visualizer.runtime import LidarVisualizer, GRAPH_PATH, PUBLISH_SETTING
from lidar_visualizer.state_publication import StatePublication
from lidar_visualizer.frame_overlay import FrameOverlay
from lidar_visualizer.reference_frames import quaternion_matrix
from isaacsim.core.simulation_manager import SimulationManager


def progress(phase):
    print('HORIZONTAL_QA', phase, flush=True)
    (OUT/'progress.json').write_text(json.dumps({'phase':phase}))


async def main():
    app = omni.kit.app.get_app()
    r = overlay = None
    report = {'scope':'13 TF edges from actual sensor frames plus 2 root edges; no RTX scans'}
    try:
        progress('enabling_extensions')
        for ext in ('isaacsim.core.nodes','isaacsim.ros2.bridge','isaacsim.ros2.nodes',
                    'isaacsim.core.experimental.prims','omni.graph.scriptnode','omni.kit.viewport.utility'):
            app.get_extension_manager().set_extension_enabled_immediate(ext, True)
        await app.next_update_async()
        ctx = omni.usd.get_context()
        await ctx.open_stage_async(str(OUT/'tf_validation_fixture.usda'))
        stage = ctx.get_stage()
        cfg = load_config(ROOT/'config/sensors.json')
        cfg['ros_domain_id'] = 151
        cfg['sensors'] = json.loads((OUT/'fixture_sensors.json').read_text())
        cfg['auto_discover'] = False
        cfg['output_directory'] = str(OUT/'captures')
        cfg = bind_config(cfg, discover_robots(stage)[0])
        cfg['robot_motion'].update(control_mode='scripted', reference_frame=cfg['root_frame'],
                                   horizontal_frame=cfg['horizontal_frame'])
        r = LidarVisualizer(ROOT, cfg, artifact_dir=OUT/'runtime')
        r.stage = stage
        r.layer = Sdf.Layer.CreateAnonymous('horizontal_tf_qa')
        stage.GetSessionLayer().subLayerPaths.insert(0, r.layer.identifier)
        r.original_publish_setting = carb.settings.get_settings().get_as_bool(PUBLISH_SETTING)
        carb.settings.get_settings().set_bool(PUBLISH_SETTING, True)
        with Usd.EditContext(stage, r.layer):
            r.motion = ArticulationMotion(stage,r.layer,cfg['robot_motion'],r._motion_error)
            r.motion.prepare()
            r.products = [None] * len(cfg['sensors'])  # TF-only graph; no render products are allocated.
            r._build_graph()
        r.state_publication = StatePublication(r)
        await r.state_publication.build(GRAPH_PATH)
        async def frames(n):
            for _ in range(n):
                await app.next_update_async()
                if overlay: overlay.update()
        progress('playing')
        r.timeline.play()
        await frames(30)
        assert r.motion.ready and not r.motion.failed, r.status
        initial = dict(r.motion.last_snapshot)
        # PhysX uses float body/joint data; initial constraint reconciliation is a few micrometres.
        np.testing.assert_allclose(initial['root_position'],[-1.124885766855359,1.600484361319494,.630280728340149],atol=1e-5)
        np.testing.assert_allclose(initial['root_xyzw'],[0,0,0,1],atol=2e-6)
        np.testing.assert_allclose(np.degrees(initial['positions']),[0,38,-106,-5.8741577631],atol=.005)
        report['initial'] = initial
        count_before = len(list(stage.Traverse()))
        overlay = FrameOverlay(r.motion)
        overlay.show()
        await frames(2)
        assert len(list(stage.Traverse())) == count_before
        report['viewport_overlay_no_usd_geometry'] = True
        bag = await r.start_recording(sensor_ids=[s['id'] for s in cfg['sensors']],output_directory=str(OUT/'captures'))
        await frames(60)
        progress('recording_and_tilting')
        r.motion.mode = 'observe'
        observations = []
        from validation.test_reference_frames import rpy_quat
        for roll,pitch,yaw in [(0,0,.6),(.25,-.3,.6),(-.2,.35,-.7)]:
            q = rpy_quat(roll,pitch,yaw)
            p = np.array(initial['root_position']) + [.2,.1,.05]
            r.motion.articulation.set_world_poses(positions=[p],orientations=[[q[3],*q[:3]]])
            r.motion.articulation.set_velocities(linear_velocities=[[0,0,0]], angular_velocities=[[0,0,0]])
            SimulationManager.get_physics_simulation_view().update_articulations_kinematic()
            omni.physx.get_physx_interface().update_transformations(False,True,False,False)
            await frames(40)
            row = dict(r.motion.last_snapshot)
            H = quaternion_matrix(row['horizontal']['xyzw'])
            np.testing.assert_allclose(H[:,2],[0,0,1],atol=2e-6)
            np.testing.assert_allclose(row['root_position'],row['horizontal']['position'],atol=1e-12)
            np.testing.assert_allclose(row['horizontal']['heading_rad'],yaw,atol=2e-3)
            S = UsdGeom.Xformable(stage.GetPrimAtPath(r.motion.reference_path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            h = UsdGeom.Xformable(stage.GetPrimAtPath(r.motion.horizontal_path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            np.testing.assert_allclose((S*h.GetInverse()).ExtractTranslation(),[0,0,0],atol=1e-10)
            observations.append(row)
        await r.stop_recording()
        report['bag_session'] = str(bag)
        report['tilt_cases'] = observations
        report['state_samples'] = r.state_publication.count
        report['expected_tf_edges'] = 15
        overlay.close(); overlay = None
        r.motion.mode = 'scripted'
        r.timeline.pause()
        r.motion.reset()
        np.testing.assert_allclose(r.motion.frame_snapshot['xyzw'],[0,0,0,1],atol=2e-6)
        r.products.clear()
        await r.close()
        assert not stage.GetPrimAtPath('/LidarVisualizerFrames')
        assert not stage.GetPrimAtPath(GRAPH_PATH)
        report['cleanup_passed'] = True
        report['passed'] = True
        progress('passed')
    except Exception:
        report['passed'] = False
        report['error'] = traceback.format_exc()
        print(report['error'], flush=True)
        if overlay:
            try: overlay.close()
            except Exception: pass
        if r:
            try:
                r.products.clear()
                await r.close()
            except Exception: pass
    (OUT/'kit_validation.json').write_text(json.dumps(report,indent=2))
    app.post_quit(0 if report.get('passed') else 1)


asyncio.ensure_future(main())
