"""Low-rate resource sampling and bounded stage timing history."""
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import threading
import time
from .contracts import write_json


class Telemetry:
    def __init__(self,directory):
        self.directory=Path(directory); self.directory.mkdir(exist_ok=True)
        self.stream=(self.directory/'timings.jsonl').open('a',encoding='utf-8',buffering=1)
        self.stop=threading.Event(); self.started=time.perf_counter()
        self.spans=defaultdict(lambda:{'count':0,'total_s':0.,'samples':deque(maxlen=4096)})
        self.phase='initializing'; self.group=-1; self.pids={'isaac':os.getpid()}
        self.thread=threading.Thread(target=self._resources,daemon=True,name='sv02-resources'); self.thread.start()

    def event(self,event,**values):
        self.stream.write(json.dumps({'event':event,'monotonic_s':time.monotonic(),
            'utc':datetime.now(timezone.utc).isoformat(),**values},allow_nan=False)+'\n')

    def measure(self,name,duration,**values):
        row=self.spans[name]; row['count']+=1; row['total_s']+=duration; row['samples'].append(duration)
        self.event('span',name=name,duration_s=duration,**values)

    def _resources(self):
        previous={}; ticks=os.sysconf('SC_CLK_TCK') if os.name=='posix' else 100
        with (self.directory/'resources.jsonl').open('a',buffering=1) as output:
            while not self.stop.is_set():
                now=time.monotonic(); result={'monotonic_s':now,'phase':self.phase,'group':self.group,'processes':{}}
                for role,pid in list(self.pids.items()):
                    try:
                        raw=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
                        cpu=(int(raw[11])+int(raw[12]))/ticks
                        memory=Path(f'/proc/{pid}/status').read_text().splitlines()
                        rss=next(int(l.split()[1])*1024 for l in memory if l.startswith('VmRSS:'))
                        prev=previous.get(pid); previous[pid]=(now,cpu)
                        result['processes'][role]={'pid':pid,'rss_bytes':rss,'cpu_cores':(cpu-prev[1])/(now-prev[0]) if prev else None}
                    except (OSError,ValueError,StopIteration): pass
                try:
                    p=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
                    result['whole_gpu']=p.stdout.strip()
                except Exception as exc: result['gpu_error']=str(exc)
                output.write(json.dumps(result)+'\n')
                self.stop.wait(1)

    def close(self):
        self.stop.set(); self.thread.join(timeout=4)
        spans={}
        for name,row in self.spans.items():
            values=sorted(row['samples'])
            spans[name]={'count':row['count'],'total_s':row['total_s'],'mean_s':row['total_s']/row['count'],
                         'recent_p95_s':values[min(len(values)-1,int(.95*len(values)))]}
        write_json(self.directory/'summary.json',{'wall_s':time.perf_counter()-self.started,'spans':spans,
            'note':'GPU values are whole-device. Spans overlap and are not GPU kernel timings.'})
        self.stream.close()
