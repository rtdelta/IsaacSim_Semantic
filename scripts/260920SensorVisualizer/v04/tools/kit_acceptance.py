"""Task-owned native GUI acceptance. Runs only v04 and never saves USD layers."""
import asyncio
from collections import defaultdict
import hashlib,json,os
from pathlib import Path
import sys,time,threading,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=Path(os.environ['SV04_TEST_OUT']);OUT.mkdir(parents=True,exist_ok=True)
phase='starting';previous=None;intervals=defaultdict(list)
report={'state':'running','captures':[]}

def save():
    (OUT/'acceptance.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
def set_phase(name):
    global phase,previous
    phase=name;previous=None
    (OUT/'phase.json').write_text(json.dumps({'phase':phase,'monotonic':time.monotonic()}))
    print('[SV04 TEST] '+name,flush=True)
def update(_):
    global previous
    now=time.monotonic()
    if previous is not None:intervals[phase].append(now-previous)
    previous=now
async def idle(app,name,seconds=3):
    set_phase(name);start=time.monotonic()
    while time.monotonic()-start<seconds:await app.next_update_async()

async def capture(panel,name,mode,groups=3,control_test=False):
    set_phase(name);panel.mode.model.get_item_value_model().set_value(0 if mode=='interactive' else 1)
    panel.groups.set_value(groups);panel.preview.set_value(mode=='interactive')
    started=time.monotonic(); task=asyncio.create_task(panel.capture());controls=[]
    # Let CapturePanel install this capture's runner before sending test controls.
    await asyncio.sleep(0)
    paused=False;resumed=False;stopped=False;pause_started=None
    # Observe group completion synchronously: a polling timer can arrive after
    # the next native render already started and accidentally resume+stop with
    # no captured group between them.
    if control_test:
        original_update=panel.runner.on_update
        def control_update(runner):
            nonlocal paused,stopped
            if original_update:original_update(runner)
            if not paused and runner.groups>=1:
                runner.pause();paused=True;controls.append('pause_requested')
            if resumed and runner.groups>=2 and not stopped:
                runner.stop();stopped=True;controls.append('stop_requested')
        panel.runner.on_update=control_update
    while not task.done():
        runner=panel.runner
        if control_test and runner:
            if paused and runner.phase=='paused' and not resumed:
                if pause_started is None:pause_started=time.monotonic()
                if time.monotonic()-pause_started>1:
                    assert all(v is False for v in panel.scene.drivers.gate.requested.values())
                    runner.resume();resumed=True;controls.append('resume_after_gated_pause')
        await asyncio.sleep(.02)
    await task
    entry={'name':name,'wall_including_writer_s':time.monotonic()-started,'session':str(panel.runner.session),
           'error':panel.runner.error,'controls':controls,'requested_updates_after':dict(panel.scene.drivers.gate.requested)}
    for file,key in (('session.json','status'),('performance/summary.json','timings'),('writer_report.json','writer')):
        path=panel.runner.session/file
        if path.exists():entry[key]=json.loads(path.read_text())
    report['captures'].append(entry);save()
    if panel.runner.error:raise RuntimeError(panel.runner.error)
    if control_test and controls!=['pause_requested','resume_after_gated_pause','stop_requested']:
        raise RuntimeError('Pause/resume/stop test did not exercise all requested transitions')

async def main():
    import omni.kit.app,omni.usd
    from sensor_visualizer_v04.contracts import DEFAULT
    from sensor_visualizer_v04.ui import CapturePanel
    app=omni.kit.app.get_app();context=omni.usd.get_context();panel=None;code=1
    subscription=app.get_update_event_stream().create_subscription_to_pop(update,name='SV04 acceptance')
    try:
        set_phase('scene_open');await context.open_stage_async(DEFAULT['scene'])
        while context.get_stage_loading_status()[2]:await app.next_update_async()
        stage=context.get_stage()
        report['assets_before']={l.realPath:hashlib.sha256(Path(l.realPath).read_bytes()).hexdigest()
            for l in stage.GetUsedLayers() if l.realPath and Path(l.realPath).is_file()}
        await idle(app,'scene_only')
        set_phase('panel_open');start=time.monotonic()
        panel=CapturePanel(ROOT);report['panel_open_s']=time.monotonic()-start
        # Create the diagnostics run in this test's output, via supported job loading.
        job=OUT/'job.json';job.write_text(json.dumps({'schema_version':3,'output_directory':str(OUT/'captures'),
            'groups':3,'mode':'offline','diagnostics':{'level':'diagnostic','export_trace_on_stop':True}}))
        panel.job_path.set_value(str(job));await panel.load()
        await idle(app,'panel_only')
        set_phase('initialize');start=time.monotonic();await panel.initialize()
        report['initialize_s']=time.monotonic()-start;report['run_diagnostics']=str(panel.diag.directory)
        report['sensor_counts']={k:len(panel.scene.registry[k]) for k in ('cameras','lidars')};save()
        await idle(app,'initialized_idle',5)
        if any(panel.scene.drivers.gate.requested.values()):raise RuntimeError('Idle sensor updates enabled')
        await capture(panel,'offline_static','offline',3)
        await idle(app,'after_capture_idle')
        # Small, valid commands relative to initial states; cab-track not touched.
        joints=panel.scene.motion.controller.states
        changes={name:{'mode':'target','target':min(s.maximum,max(s.minimum,s.angle+2)), 'speed':2} for name,s in joints.items()}
        panel.scene.apply_commands({'joints':changes,'tilt':{'pitch':{'mode':'target','target':2,'speed':2}}})
        await capture(panel,'interactive_motion_pause_stop','interactive',10,True)
        await idle(app,'after_stop_idle')
        # A reversible mount edit must resynchronize at frozen time.
        editable=[p for p in panel.scene.poses.snapshot() if p['editable']]
        if editable:
            row=editable[0];position=list(row['position_m']);position[2]+=.01
            panel.scene.poses.apply(row['id'],position,row['rotation_deg'])
            await capture(panel,'mount_resync','offline',2)
        await panel.close();await idle(app,'after_close_idle')
        report['assets_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in report['assets_before'].items())
        if not report['assets_unchanged']:raise RuntimeError('Asset file changed')
        report['state']='finished';code=0
    except Exception:
        report.update(state='failed',error=traceback.format_exc());traceback.print_exc()
    finally:
        if panel and not panel.closed:
            try:await panel.close()
            except Exception:report['cleanup_error']=traceback.format_exc()
        report['frame_intervals']={name:{'count':len(v),'mean_s':sum(v)/len(v),'p50_s':sorted(v)[len(v)//2],
            'p95_s':sorted(v)[min(len(v)-1,int(.95*len(v)))],'max_s':max(v)} for name,v in intervals.items() if v}
        save();subscription=None
        print('[SV04 TEST RESULT] '+str(OUT/'acceptance.json'),flush=True)
        timer=threading.Timer(20,lambda:os._exit(code));timer.daemon=True;timer.start();app.post_quit(code)

_sv04_acceptance_task=asyncio.ensure_future(main())
