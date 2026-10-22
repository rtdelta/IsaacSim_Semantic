"""Temporary external test harness. Never writes application source or asset layers."""
import asyncio
import builtins
from collections import defaultdict
from datetime import datetime, timezone
import functools
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time
import traceback

ROOT = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
phase = 'startup'
events = (OUT/'events.jsonl').open('a', buffering=1)
stats = defaultdict(lambda: {'count': 0, 'total_s': 0., 'max_s': 0.})
frames = defaultdict(list)
previous_update = None
report = {'state': 'running', 'phases': [], 'captures': [], 'scope': 'isolated GUI process; original source unmodified'}

def event(kind, **data):
    events.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'mono': time.monotonic(),
                            'phase': phase, 'kind': kind, **data}, default=str)+'\n')

def set_phase(name):
    global phase, previous_update
    phase = name; previous_update = None
    (OUT/'phase.json').write_text(json.dumps({'phase': phase, 'monotonic': time.monotonic()}))
    event('phase_begin')
    print('[PERF_PHASE] '+name, flush=True)

def account(name, duration):
    row = stats[(phase, name)]; row['count'] += 1
    row['total_s'] += duration; row['max_s'] = max(row['max_s'], duration)

def instrument_sync(cls, name):
    original = getattr(cls, name)
    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        except Exception as exc:
            if name == 'read': event('read_exception', error=repr(exc))
            raise
        finally: account(cls.__name__+'.'+name, time.perf_counter()-start)
    setattr(cls, name, wrapper)

def instrument_async(cls, name):
    original = getattr(cls, name)
    @functools.wraps(original)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            value = await original(*args, **kwargs)
            if name == 'capture':
                event('capture_bundle', group=value[1]['group_id'], stamp=value[1]['simulation_time_ns'],
                      retries=value[1]['frozen_render_retries'])
            return value
        finally:
            duration = time.perf_counter()-start
            account(cls.__name__+'.'+name, duration)
            if name in ('render', 'advance', 'warm_cameras'):
                event('call', function=cls.__name__+'.'+name, argument=args[1] if len(args)>1 else None, duration_s=duration)
    setattr(cls, name, wrapper)

def update_callback(_):
    global previous_update
    now = time.perf_counter()
    if previous_update is not None: frames[phase].append(now-previous_update)
    previous_update = now

def save_report():
    report['call_stats'] = {p: {name: values for (other, name), values in stats.items() if other == p}
                            for p, _ in stats}
    report['frame_intervals'] = {}
    for name, values in frames.items():
        if not values: continue
        ordered = sorted(values)
        report['frame_intervals'][name] = {'count': len(values), 'mean_s': sum(values)/len(values),
            'p50_s': ordered[len(ordered)//2], 'p95_s': ordered[min(len(ordered)-1, int(.95*len(ordered)))],
            'max_s': max(values)}
    (OUT/'report.json').write_text(json.dumps(report, indent=2, default=str)+'\n')

async def idle(app, name, seconds=4):
    set_phase(name); started=time.perf_counter()
    while time.perf_counter()-started < seconds: await app.next_update_async()
    report['phases'].append({'name': name, 'wall_s': time.perf_counter()-started})
    save_report()

async def capture(panel, name, warmup, suppress_lidar_advance=False):
    set_phase(name)
    panel.job['render']['camera_subframes'] = warmup
    panel.groups.set_value(3)
    # Keep the original UI defaults: interactive, ROS preview on, 10 Hz.
    original_advance = panel.scene.advance
    if suppress_lidar_advance:
        async def experimental_advance(group):
            for product in panel.scene.drivers.lidar_products: product.hydra_texture.set_updates_enabled(False)
            try: return await original_advance(group)
            finally:
                for product in panel.scene.drivers.lidar_products: product.hydra_texture.set_updates_enabled(True)
        panel.scene.advance = experimental_advance
    started=time.perf_counter()
    try:
        await asyncio.create_task(panel.capture())
        entry={'name': name, 'wall_including_writer_s': time.perf_counter()-started,
               'session': str(panel.runner.session), 'error': panel.runner.error}
        for relative, key in [('session.json','status'), ('performance/summary.json','timings'),
                              ('writer_status.json','writer')]:
            path=panel.runner.session/relative
            if path.is_file(): entry[key]=json.loads(path.read_text())
        report['captures'].append(entry)
        save_report()
        if panel.runner.error: raise RuntimeError(panel.runner.error)
    finally: panel.scene.advance = original_advance

async def main():
    import omni.kit.app
    import omni.usd
    import carb.settings
    app=omni.kit.app.get_app(); context=omni.usd.get_context()
    subscription=app.get_update_event_stream().create_subscription_to_pop(update_callback, name='sv02_external_diagnostic')
    panel=None; code=1
    try:
        from sensor_visualizer_v02.contracts import DEFAULT
        set_phase('open_scene'); start=time.perf_counter()
        await context.open_stage_async(DEFAULT['scene'])
        deadline=time.monotonic()+180
        while context.get_stage_loading_status()[2]:
            if time.monotonic()>deadline: raise TimeoutError('USD load')
            await app.next_update_async()
        report['scene_open_s']=time.perf_counter()-start
        stage=context.get_stage()
        report['asset_hashes_before']={l.realPath:hashlib.sha256(Path(l.realPath).read_bytes()).hexdigest()
            for l in stage.GetUsedLayers() if l.realPath and Path(l.realPath).is_file()}
        settings=carb.settings.get_settings()
        keys=('/rtx/rendermode','/rtx/post/dlss/execMode','/app/asyncRendering',
              '/app/runLoops/main/rateLimitEnabled','/app/runLoops/main/rateLimitFrequency')
        report['settings_before']={key:settings.get(key) for key in keys}
        await idle(app,'scene_only',8)
        set_phase('script_editor_run'); start=time.perf_counter()
        namespace=runpy.run_path(str(ROOT/'run_in_isaac.py'))
        await namespace['_task']
        report['panel_launch_s']=time.perf_counter()-start
        panel=builtins._sensor_visualizer_v02
        await idle(app,'panel_only',5)
        set_phase('instrument_imports')
        from sensor_visualizer_v02.scene import SceneStepper
        from sensor_visualizer_v02.sensors import SensorDrivers
        from sv02_legacy.articulation_motion import ArticulationMotion
        for cls,names in ((SensorDrivers,('__init__','_receive','read')),
                          (SceneStepper,('_pose_matrices',)),
                          (ArticulationMotion,('prepare','_apply_controlled_base','snapshot'))):
            for name in names: instrument_sync(cls,name)
        for cls,names in ((SceneStepper,('advance','capture')), (SensorDrivers,('render','warm_cameras'))):
            for name in names: instrument_async(cls,name)
        panel.job['output_directory']=str(OUT/'captures')
        set_phase('initialize'); start=time.perf_counter()
        await panel.initialize()
        report['initialize_s']=time.perf_counter()-start
        report['sensor_counts']={k:len(panel.scene.registry[k]) for k in ('cameras','lidars')}
        report['settings_initialized']={key:settings.get(key) for key in keys}
        await idle(app,'initialized_idle',5)
        for product in panel.scene.drivers.lidar_products: product.hydra_texture.set_updates_enabled(False)
        await idle(app,'idle_lidars_disabled',5)
        for product in panel.scene.drivers.lidar_products: product.hydra_texture.set_updates_enabled(True)
        await idle(app,'idle_lidars_restored',5)
        await capture(panel,'default_capture_warm16',16)
        await idle(app,'after_stop_idle',4)
        await capture(panel,'ab_capture_warm1',1)
        await capture(panel,'ab_warm1_lidar_off_during_advance',1,True)
        await capture(panel,'repeat_default_warm16',16)
        set_phase('close_panel'); start=time.perf_counter()
        await panel.close()
        report['panel_close_s']=time.perf_counter()-start
        await idle(app,'after_close_idle',4)
        report['settings_after_close']={key:settings.get(key) for key in keys}
        report['asset_hashes_after']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in report['asset_hashes_before']}
        report['assets_unchanged']=report['asset_hashes_before']==report['asset_hashes_after']
        report['state']='finished'; code=0
    except Exception:
        report.update(state='failed',error=traceback.format_exc()); traceback.print_exc()
    finally:
        set_phase('cleanup')
        if panel and not panel.closed:
            try: await panel.close()
            except Exception: report['cleanup_error']=traceback.format_exc()
        save_report(); event('finished',state=report['state'])
        subscription=None; events.close()
        print('[PERF_RESULT] '+str(OUT/'report.json'),flush=True)
        timer=threading.Timer(20,lambda:os._exit(code)); timer.daemon=True; timer.start()
        app.post_quit(code)

_task=asyncio.ensure_future(main())
