from pathlib import Path
import json,os,signal
p=Path('/root/gpufree-data/semantic/output/sensor_visualizer/diagnostics/20261008_perf_01/process.json')
r=json.loads(p.read_text()); pid=r['pid']; stat=Path(f'/proc/{pid}/stat')
if stat.exists():
    fields=stat.read_text().rsplit(')',1)[1].split()
    if fields[19]!=r['identity']['start']: raise RuntimeError('PID identity changed')
    cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
    if b'/20261008_perf_01/kit_profile.py' not in cmd: raise RuntimeError('Not task-owned test')
    os.killpg(pid,signal.SIGKILL)
    print(json.dumps({'terminated_test_pid':pid,'reason':'Diagnostic launcher used incorrect display; no source modified'}))
else: print('Task process already exited')
