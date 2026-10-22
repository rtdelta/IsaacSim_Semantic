"""Low-rate device NVML and /proc samples. Whole-device values are not process counters."""
import ctypes as C
import json,os,threading,time
from pathlib import Path

class Util(C.Structure):_fields_=[('gpu',C.c_uint),('memory',C.c_uint)]
class Memory(C.Structure):_fields_=[('total',C.c_ulonglong),('free',C.c_ulonglong),('used',C.c_ulonglong)]

class Sampler:
    def __init__(self,directory,pid_file):
        self.directory=Path(directory);self.pid_file=Path(pid_file);self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,name='sl06-resources',daemon=True)
    def start(self):self.thread.start()
    def close(self):self.stop.set();self.thread.join(timeout=5)
    def gpu(self):
        if not hasattr(self,'nvml'):
            self.nvml=C.CDLL('libnvidia-ml.so.1')
            if self.nvml.nvmlInit_v2()!=0:raise RuntimeError('NVML init failed')
            self.handle=C.c_void_p()
            if self.nvml.nvmlDeviceGetHandleByIndex_v2(C.c_uint(0),C.byref(self.handle))!=0:raise RuntimeError('NVML device 0 unavailable')
        out={'index':0,'scope':'whole GPU device; other processes may contribute'}
        u=Util();m=Memory()
        if self.nvml.nvmlDeviceGetUtilizationRates(self.handle,C.byref(u))==0:out.update(gpu_percent=u.gpu,memory_busy_percent=u.memory)
        if self.nvml.nvmlDeviceGetMemoryInfo(self.handle,C.byref(m))==0:out.update(memory_used_bytes=m.used,memory_total_bytes=m.total)
        for name,fn,kind in (('sm_clock_mhz','nvmlDeviceGetClockInfo',1),('memory_clock_mhz','nvmlDeviceGetClockInfo',2),
                             ('pcie_tx_kb_s','nvmlDeviceGetPcieThroughput',0),('pcie_rx_kb_s','nvmlDeviceGetPcieThroughput',1)):
            v=C.c_uint();function=getattr(self.nvml,fn,None)
            if function and function(self.handle,C.c_uint(kind),C.byref(v))==0:out[name]=v.value
            else:out[name]=None
        return out
    def run(self):
        with (self.directory/'system_resources.jsonl').open('x',encoding='utf-8') as f:
            while not self.stop.is_set():
                row={'host_monotonic_ns':time.monotonic_ns(),'utc_ns':time.time_ns()}
                try:row['gpu']=self.gpu()
                except Exception as exc:row['gpu_error']=type(exc).__name__+': '+str(exc)
                try:
                    pid=int(self.pid_file.read_text());p=Path('/proc')/str(pid)
                    s=(p/'stat').read_text().rsplit(')',1)[1].split()
                    row['process']={'pid':pid,'start_ticks':int(s[19]),'user_ticks':int(s[11]),'system_ticks':int(s[12]),
                        'rss_pages':int(s[21]),'clock_ticks_per_second':os.sysconf('SC_CLK_TCK'),'page_size':os.sysconf('SC_PAGE_SIZE')}
                    row['process']['threads']={}
                    for t in (p/'task').iterdir():
                        try:
                            v=(t/'stat').read_text().rsplit(')',1)[1].split()
                            row['process']['threads'][t.name]={'user_ticks':int(v[11]),'system_ticks':int(v[12]),'cpu':int(v[36])}
                        except (OSError,ValueError):pass
                except (OSError,ValueError):row['process']=None
                f.write(json.dumps(row)+'\n');f.flush();self.stop.wait(1)
        if hasattr(self,'nvml'):self.nvml.nvmlShutdown()
