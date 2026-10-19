import json,os,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05')
directory=root/'reports/native_owner';directory.mkdir(parents=True,exist_ok=True)
options=json.loads((directory/'owner_test_options.json').read_text()) if (directory/'owner_test_options.json').exists() else {}
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:raw=(p/'cmdline').read_bytes()
        except OSError:continue
        if b'/kit/kit' in raw and not options.get('allow_other_kit'):raise RuntimeError('Another Kit is running; preserve it and postpone native test')
env=os.environ.copy();env.update(SV05_OWNER_TEST='2700',SV05_SOCKET='/root/gpufree-data/semantic/output/sensor_visualizer/v05/runtime/test_engine.sock')
if options.get('native_event_test'):env['SV05_NATIVE_EVENT_TEST']='1'
gui=bool(options.get('gui'))
if gui:
    displays=list(Path('/tmp/.X11-unix').glob('X*'));assert len(displays)==1,'Identify the desktop display before launching'
    env['DISPLAY']=':'+displays[0].name[1:]
logpath=directory/('kit_'+str(time.time_ns())+'.log');log=logpath.open('xb')
p=subprocess.Popen(['/usr/bin/python3',str(root/'run_capture.py'),'--interactive' if gui else '--headless-owner'],cwd=root,env=env,
    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
row={'pid':p.pid,'started_ns':time.monotonic_ns(),'log':str(logpath),'socket':env['SV05_SOCKET'],'gui':gui}
(directory/'owner.json').write_text(json.dumps(row));print(json.dumps(row))
