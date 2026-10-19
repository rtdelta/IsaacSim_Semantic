"""Identical task-owned measurements for v05 and v06; no baseline files edited."""
import asyncio,importlib,json,os,sys,time
from collections import defaultdict
from pathlib import Path
ROOT=Path(os.environ['SV_BENCH_ROOT']);VERSION=ROOT.name;sys.path.insert(0,str(ROOT))
DIR=Path(os.environ['SV_BENCH_DIR']);DIR.mkdir(parents=True,exist_ok=True)
stats=defaultdict(lambda:{'count':0,'wall_ns':0,'cpu_ns':0,'max_ns':0,'recent':[]})
def wrap(cls,name):
    fn=getattr(cls,name)
    def measured(*a,**k):
        start=time.monotonic_ns();cpu=time.thread_time_ns()
        try:return fn(*a,**k)
        finally:
            elapsed=time.monotonic_ns()-start;row=stats[name];row['count']+=1;row['wall_ns']+=elapsed
            row['cpu_ns']+=time.thread_time_ns()-cpu;row['max_ns']=max(row['max_ns'],elapsed)
            row['recent'].append(elapsed)
            if len(row['recent'])>10000:del row['recent'][:1000]
            if elapsed>50_000_000:
                with (DIR/'sdk_outliers.jsonl').open('a') as stream:
                    stream.write(json.dumps({'method':name,'start_ns':start,'duration_ns':elapsed,
                        'thread_cpu_ns':time.thread_time_ns()-cpu,'pid':os.getpid()})+'\n')
    setattr(cls,name,measured)
async def main():
    import omni.kit.app,carb.settings
    pkg='sensor_visualizer_'+VERSION
    Runtime=importlib.import_module(pkg+'.interactive_runtime').InteractiveRuntime
    Motion=importlib.import_module(pkg+'.robot.articulation_motion').ArticulationMotion
    for name in ('_apply','_apply_controlled_base','_update_reference','snapshot'):wrap(Motion,name)
    for name in ('_update','_commit','publish','command'):wrap(Runtime,name)
    global runtime
    (DIR/'owner_output/runtime').mkdir(parents=True,exist_ok=True)
    runtime=Runtime(ROOT,output=DIR/'owner_output',socket_path=DIR/'engine.sock')
    options=json.loads((DIR/'spec.json').read_text()).get('interactive_overrides',{})
    if options:
        merge=importlib.import_module(pkg+'.contracts').merge;runtime.job=merge(runtime.job,options)
    await runtime.initialize(open_scene=True)
    time_limit=time.monotonic()+1200
    values=runtime.scene.motion.articulation.get_world_poses()
    capability={'version':VERSION,'pid':os.getpid(),'physics_arrays':[{'type':type(v).__name__,'device':str(getattr(v,'device','unknown'))} for v in values],
        'renderer_active_gpu':carb.settings.get_settings().get('/renderer/activeGpu'),
        'physics_cuda_device':carb.settings.get_settings().get('/physics/cudaDevice'),
        'sensor_products':runtime.scene.render_actual['sensor_products_created'],'clock':'same-host monotonic_ns'}
    capability['interactive_options']=runtime.job.get('interactive',{})
    (DIR/'owner_ready.json').write_text(json.dumps(capability,indent=2))
    while not runtime.closed and time.monotonic()<time_limit:
        await asyncio.sleep(1)
        summary={name:{**{k:v for k,v in row.items() if k!='recent'},'p95_ns':sorted(row['recent'])[int(.95*(len(row['recent'])-1))]} for name,row in stats.items()}
        tmp=DIR/'sdk_profile.tmp';tmp.write_text(json.dumps(summary));tmp.replace(DIR/'sdk_profile.json')
    await runtime.close();omni.kit.app.get_app().post_quit(0)
task=asyncio.ensure_future(main())
def done(t):
    if not t.cancelled() and t.exception():
        import traceback,omni.kit.app
        traceback.print_exception(t.exception());omni.kit.app.get_app().post_quit(1)
task.add_done_callback(done)
