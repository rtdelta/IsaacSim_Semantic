"""Kit --exec: bounded one-camera/one-Instant-LiDAR timing experiment."""
import asyncio
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import omni.kit.app
import omni.usd
import omni.timeline
import omni.replicator.core as rep
from pxr import Usd, UsdGeom, Sdf
from isaacsim.core.simulation_manager import SimulationManager


def summary(value):
    if isinstance(value, dict):
        return {str(k): summary(v) for k, v in value.items()}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    try:
        a = value.numpy() if hasattr(value, 'numpy') else np.asarray(value)
        return {'shape': list(a.shape), 'dtype': str(a.dtype), 'first': a.reshape(-1)[:16].tolist()}
    except Exception:
        return {'type': str(type(value))}


async def main():
    report = {'state': 'running', 'samples': []}
    destination = ROOT/'reports/probe_capture.json'
    destination.parent.mkdir(exist_ok=True)
    def save():
        destination.write_text(json.dumps(report, indent=2, default=str)+'\n')
    app = omni.kit.app.get_app()
    products, annotators = [], []
    motion = None
    try:
        context = omni.usd.get_context()
        await context.open_stage_async('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
        for _ in range(600):
            if context.get_stage_loading_status()[2] == 0: break
            await app.next_update_async()
        else: raise RuntimeError('USD loading timeout')
        stage = context.get_stage()
        layer = Sdf.Layer.CreateAnonymous('sv02_probe.usda')
        stage.GetSessionLayer().subLayerPaths.insert(0, layer.identifier)
        stage.SetEditTarget(layer)
        from sv02_legacy.discovery import discover_sensors
        from sv02_legacy.render_lease import RenderLease
        from sv02_legacy.robot_discovery import discover_robots, bind_config
        from sv02_legacy.articulation_motion import ArticulationMotion
        sensors = discover_sensors(stage)
        report['sensor_scan_modes'] = {s['id']: {a.GetName(): str(a.Get()) for a in stage.GetPrimAtPath(s['prim_path']).GetAttributes()
                                        if any(k in a.GetName().lower() for k in ('scantype', 'tickrate', 'scanrate', 'reporttype'))} for s in sensors}
        sensor = next(s for s in sensors if 'Airy' in s['id'] and 'front' in s['id'])
        camera = '/World/Excavator/swing_link/FisheyeFront'
        report['lidar'] = sensor
        lease = RenderLease(stage, layer, [s['prim_path'] for s in sensors] + [camera])
        report['lease'] = lease.metadata()
        cfg = json.loads((ROOT/'config/legacy_sensors.json').read_text())
        robots = [r for r in discover_robots(stage) if r['auto_eligible']]
        if len(robots) != 1: raise RuntimeError('Ambiguous robot')
        cfg = bind_config(cfg, robots[0])
        cfg['robot_motion'].update(reference_frame=cfg['root_frame'], horizontal_frame=cfg['horizontal_frame'], control_mode='scripted')
        motion = ArticulationMotion(stage, layer, cfg['robot_motion'], lambda error: report.update(motion_error=error))
        motion.prepare()
        rep.orchestrator.set_capture_on_play(False)
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        for _ in range(6): await app.next_update_async()
        timeline.pause()
        timeline.commit()
        motion.tick(timeline.get_current_time())
        if not motion.ready: raise RuntimeError('Articulation not initialized')
        report['initial_state'] = motion.snapshot(timeline.get_current_time())
        report['clock_start'] = timeline.get_current_time()
        cam = stage.GetPrimAtPath(camera)
        size = tuple(int(v) for v in cam.GetAttribute('omni:lensdistortion:opencvFisheye:imageSize').Get())
        camera_product = rep.create.render_product(camera, size, name='SV02_ProbeCamera', force_new=True)
        lidar_product = rep.create.render_product(sensor['prim_path'], (300, 300), name='SV02_ProbeLidar', force_new=True)
        products += [camera_product, lidar_product]
        for name, product in [('rgb', camera_product), ('CameraParams', camera_product), ('IsaacReadSimulationTime', camera_product),
                               ('IsaacExtractRTXSensorPointCloud', lidar_product), ('IsaacReadSimulationTime', lidar_product)]:
            annot = rep.AnnotatorRegistry.get_annotator(name, device='cpu')
            if name == 'IsaacReadSimulationTime': annot.initialize(resetOnStop=True)
            annot.attach([product.path])
            annotators.append((name, product, annot))
        # Finish Replicator's initialization before defining the recorded epoch.
        await rep.orchestrator.step_async(delta_time=0.0, pause_timeline=True, rt_subframes=4, wait_for_render=True)
        sensor_world = UsdGeom.Xformable(stage.GetPrimAtPath(sensor['prim_path'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        from pxr import Gf
        target_position = sensor_world.Transform(Gf.Vec3d(0, 0, 5))
        cube = UsdGeom.Cube.Define(stage, '/SV02ProbeTarget')
        cube.CreateSizeAttr(1.0)
        cube.AddTranslateOp().Set(target_position)
        report['target_world'] = list(target_position)
        for index in range(4):
            if index == 2:
                c = motion.base_controller
                c.direct(c.x + 0.25, c.y, np.rad2deg(c.heading) + 10)
                motion._apply_controlled_base(motion._command_angles())
                timeline.play()
                timeline.commit()
                for _ in range(6): await app.next_update_async()
                timeline.pause()
                timeline.commit()
                motion._apply_controlled_base(motion._command_angles())
            before = timeline.get_current_time()
            native_before = SimulationManager.get_simulation_time()
            await rep.orchestrator.step_async(delta_time=0.0, pause_timeline=True, rt_subframes=4, wait_for_render=True)
            row = {'index': index, 'timeline_before': before, 'timeline_after': timeline.get_current_time(), 'playing_after': timeline.is_playing()}
            row.update(native_before=native_before, native_after=SimulationManager.get_simulation_time())
            for i, (name, product, annot) in enumerate(annotators):
                data = annot.get_data()
                row[str(i)+'_'+name] = summary(data)
                if name == 'rgb':
                    from PIL import Image
                    a = data['data'] if isinstance(data, dict) else data
                    Image.fromarray(np.asarray(a)[:, :, :3]).save(ROOT/f'reports/probe_{index}.png', compress_level=1)
                if name == 'IsaacExtractRTXSensorPointCloud':
                    np.save(ROOT/f'reports/probe_cloud_{index}.npy', data.get('data', data) if isinstance(data, dict) else data)
                    points = np.asarray(data['data'])
                    tf = np.asarray(data['info']['transform']).reshape(4,4)
                    world = points @ tf[:3,:3] + tf[3,:3]
                    delta = np.abs(world-np.asarray(target_position))
                    inside = (delta <= 0.53).all(axis=1)
                    row['known_target_hits'] = int(inside.sum())
                    row['target_face_max_error'] = float(np.abs(delta[inside].max(axis=1)-0.5).max()) if inside.any() else None
                    authored = np.asarray(UsdGeom.Xformable(stage.GetPrimAtPath(sensor['prim_path'])).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
                    row['lidar_render_pose_error'] = float(np.abs(tf-authored).max())
            row['camera_usd_to_world'] = list(map(list, UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(Usd.TimeCode.Default())))
            row['robot_snapshot'] = motion.snapshot(before)
            report['samples'].append(row)
            save()
        report['state'] = 'finished'
    except Exception:
        report.update(state='failed', error=traceback.format_exc())
        print(report['error'], flush=True)
    finally:
        save()
        for _, product, annot in reversed(annotators):
            try: annot.detach([product.path])
            except Exception: pass
        for product in reversed(products):
            try: product.destroy()
            except Exception: pass
        print('[SV02_PROBE_RESULT] '+str(destination), flush=True)
        code = 0 if report['state'] == 'finished' else 1
        # Bound native Kit teardown after this task's outputs are completely closed.
        import threading, os
        threading.Timer(15, lambda: os._exit(code)).start()
        app.post_quit(code)

_sv02_probe_task = asyncio.ensure_future(main())
