"""Synchronous owner spans: bounded CPU/wall counters, sampled detail and slow frames."""
from collections import defaultdict,deque
from contextlib import contextmanager
import time

class HotPathMetrics:
    def __init__(self,diagnostics,sample_every=30):
        self.diag=diagnostics;self.sample_every=sample_every;self.index=0;self.rows=None;self.last_report=0
        self.counters=defaultdict(lambda:{'count':0,'wall_ns':0,'cpu_ns':0,'max_ns':0,'recent':deque(maxlen=512)})
    def begin_frame(self):
        self.index+=1;self.rows=[];self.started=time.monotonic_ns();self.cpu_started=time.thread_time_ns()
    @contextmanager
    def span(self,name):
        start=time.monotonic_ns();cpu=time.thread_time_ns()
        try:yield
        finally:
            wall=time.monotonic_ns()-start;used=time.thread_time_ns()-cpu
            r=self.counters[name];r['count']+=1;r['wall_ns']+=wall;r['cpu_ns']+=used;r['max_ns']=max(r['max_ns'],wall);r['recent'].append(wall)
            if self.rows is not None:self.rows.append({'name':name,'start_ns':start,'wall_ns':wall,'thread_cpu_ns':used})
    def finish_frame(self,**context):
        wall=time.monotonic_ns()-self.started;cpu=time.thread_time_ns()-self.cpu_started
        if wall>50_000_000 or self.index%self.sample_every==0:
            self.diag.event('interactive_frame',critical=wall>50_000_000,frame_index=self.index,
                duration_ns=wall,thread_cpu_duration_ns=cpu,spans=self.rows,
                timing_scope='synchronous owner thread; nested spans inclusive',**context)
        if time.monotonic()-self.last_report>1:
            snapshot={k:{**{n:v for n,v in r.items() if n!='recent'},'p95_recent_ns':sorted(r['recent'])[min(len(r['recent'])-1,int(len(r['recent'])*.95))]} for k,r in self.counters.items()}
            self.diag.event('interactive_hotspots',frame_index=self.index,counters=snapshot,**context);self.last_report=time.monotonic()
        self.rows=None
