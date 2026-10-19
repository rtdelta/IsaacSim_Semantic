"""Background /proc and existing nvidia-smi sampling; no package installation."""
from pathlib import Path
import os
import shutil
import subprocess
import threading
import time


class ResourceSampler:
    def __init__(self, diagnostics):
        self.diag=diagnostics; self.pids={'isaac':os.getpid()}; self.previous={}
        self.stop=threading.Event(); self.smi=shutil.which('nvidia-smi')
        self.thread=threading.Thread(target=self.run, name='s0602-resources', daemon=True); self.thread.start()

    def stat(self, path, key):
        fields=path.read_text().rsplit(')',1)[1].split()
        cpu=(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
        now=time.monotonic(); previous=self.previous.get(key); self.previous[key]=(now,cpu)
        return {'cpu_cores':(cpu-previous[1])/(now-previous[0]) if previous else None}

    def run(self):
        while not self.stop.is_set():
            result={'processes':{}, 'gpu_source':'nvidia-smi whole-device; not SM occupancy'}
            for role,pid in list(self.pids.items()):
                try:
                    row=self.stat(Path(f'/proc/{pid}/stat'),pid); row['pid']=pid
                    status=Path(f'/proc/{pid}/status').read_text().splitlines()
                    row['rss_bytes']=next(int(x.split()[1])*1024 for x in status if x.startswith('VmRSS:'))
                    row['main_thread']=self.stat(Path(f'/proc/{pid}/task/{pid}/stat'),(pid,pid))
                    result['processes'][role]=row
                except (OSError,ValueError,StopIteration): pass
            for name in ('cpu.max','cpu.stat','memory.current','memory.max'):
                try: result['cgroup_'+name]=Path('/sys/fs/cgroup',name).read_text().strip()
                except OSError: pass
            if self.smi:
                try:
                    r=subprocess.run([self.smi,'--query-gpu=index,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],
                                     capture_output=True,text=True,timeout=2)
                    result['whole_gpu']=r.stdout.strip(); result['gpu_query_returncode']=r.returncode
                except (OSError,subprocess.TimeoutExpired) as exc: result['gpu_error']=str(exc)
            self.diag.event('resource_sample', **result)
            self.stop.wait(self.diag.config['resource_period_ms']/1000)

    def close(self): self.stop.set(); self.thread.join(timeout=3)
