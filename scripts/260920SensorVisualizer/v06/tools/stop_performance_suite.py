"""Only stop PIDs from this suite's own launch records; never use process names."""
import json,os,signal,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
info=json.loads((root/'reports/latest_performance_suite.json').read_text());out=Path(info['directory']);stopped=[]
rows=[json.loads(p.read_text()) for p in out.glob('*_process.json')]+[{'pid':info['pid'],'supervisor':True}]
for row in rows:
    pid=row['pid'];p=Path('/proc',str(pid))
    if not (p/'cmdline').exists():continue
    raw=(p/'cmdline').read_bytes()
    if not raw:continue
    if row.get('start_ticks'):assert (p/'stat').read_text().rsplit(')',1)[1].split()[19]==row['start_ticks']
    if row.get('supervisor'):assert str(root/'tools/performance_suite.py').encode() in raw and str(out/'spec.json').encode() in raw
    else:assert str(root/'tools/benchmark_entry.py').encode() in raw or str(out).encode() in raw
    os.kill(pid,signal.SIGTERM);stopped.append(pid)
    deadline=time.monotonic()+20
    while (p/'cmdline').exists() and (p/'cmdline').read_bytes() and time.monotonic()<deadline:time.sleep(.1)
    if (p/'cmdline').exists() and (p/'cmdline').read_bytes():
        assert (p/'cmdline').read_bytes()==raw;os.kill(pid,signal.SIGKILL)
print(json.dumps({'stopped_owned':stopped}))
