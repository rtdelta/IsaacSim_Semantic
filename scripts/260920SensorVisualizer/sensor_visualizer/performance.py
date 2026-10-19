"""Bounded instrumentation; batched disk IO off the Kit main thread."""
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid


def timed(name):
    def decorate(function):
        @wraps(function)
        def measured(self, *args, **kwargs):
            monitor = getattr(self, 'performance', None)
            if monitor is None: monitor = getattr(getattr(self, 'runtime', None), 'performance', None)
            if monitor is None: return function(self, *args, **kwargs)
            with monitor.span(name): return function(self, *args, **kwargs)
        return measured
    return decorate


class Performance:
    def __init__(self, project, output):
        self.started = time.monotonic()
        self.directory = Path(output)/'_performance'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
        self.directory.mkdir(parents=True,exist_ok=False)
        self.events=queue.Queue(maxsize=16384)
        self.dropped=0
        self.metrics=defaultdict(lambda:dict(count=0,total_s=0.,max_s=0.,recent=deque(maxlen=4096)))
        self.state=dict(phase='initializing',playing=False,simulation_time=0.,tracked_pids={'isaac':os.getpid()})
        self.halt=threading.Event()
        self.error=None
        self.active_wall=self.active_sim=0.
        self.previous=None
        self.child=None
        self.thread=threading.Thread(target=self._worker,name='SensorVisualizerMetrics',daemon=True)
        self.thread.start()
        if os.name == 'posix':
            from .recording import ros_environment
            self.child=subprocess.Popen(['/usr/bin/python3','-I','-S','-B',str(Path(project)/'tools/monitor_resources.py'),
                '--pid',str(os.getpid()),'--directory',str(self.directory)],
                env=ros_environment({'ros_domain_id':0}),stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        self.event('runtime_started')

    def event(self, event_name, **values):
        row=dict(event=event_name,monotonic_s=time.monotonic(),utc=datetime.now(timezone.utc).isoformat(),**values)
        try:self.events.put_nowait(row)
        except queue.Full:self.dropped+=1

    @contextmanager
    def span(self, name):
        started=time.perf_counter()
        try:yield
        finally:self.event('span',name=name,duration_s=time.perf_counter()-started)

    def update(self, simulation_time, playing, phase, **values):
        now=time.monotonic()
        if self.previous:
            old_wall,old_sim,was_playing=self.previous
            if playing and was_playing and simulation_time>=old_sim:
                self.active_wall+=now-old_wall;self.active_sim+=simulation_time-old_sim
        self.previous=(now,simulation_time,playing)
        if self.state['phase']!=phase:self.event('phase',phase=phase,simulation_time=simulation_time)
        self.state=dict(self.state,phase=phase,playing=playing,simulation_time=simulation_time,
            runtime_wall_s=now-self.started,active_play_wall_s=self.active_wall,
            active_simulation_s=self.active_sim,active_play_rtf=self.active_sim/self.active_wall if self.active_wall else None,
            last_update_monotonic_s=now,**values)

    def track(self, role, process):
        pids=dict(self.state['tracked_pids'])
        if process is None:pids.pop(role,None)
        else:pids[role]=process.pid
        self.state=dict(self.state,tracked_pids=pids)

    def _json(self, name, data):
        path=self.directory/name; temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8');temp.replace(path)

    def _summary(self):
        spans={}
        for name,m in self.metrics.items():
            values=sorted(m['recent'])
            spans[name]=dict(count=m['count'],total_s=m['total_s'],mean_ms=1000*m['total_s']/m['count'],
                max_ms=1000*m['max_s'],recent_p95_ms=1000*values[min(len(values)-1,int(.95*len(values)))],
                percentile_window=len(values))
        return dict(state=self.state,spans=spans,dropped_telemetry_events=self.dropped,error=self.error,
            notes=['Spans can be nested; do not sum them as exclusive CPU/GPU time.',
                   'pacing.wait measures explicit Python waiting; Kit native limiter may add waiting.',
                   'callback wall times and frame intervals do not measure GPU kernel duration.'])

    def _worker(self):
        try:
            with (self.directory/'timings.jsonl').open('a',encoding='utf-8') as stream:
                next_flush=0.
                while not self.halt.is_set() or not self.events.empty():
                    try:row=self.events.get(timeout=.2)
                    except queue.Empty:row=None
                    if row is not None:
                        stream.write(json.dumps(row,separators=(',',':'))+'\n')
                        if row['event']=='span':
                            m=self.metrics[row['name']];duration=row['duration_s']
                            m['count']+=1;m['total_s']+=duration;m['max_s']=max(m['max_s'],duration);m['recent'].append(duration)
                    if time.monotonic()>=next_flush:
                        next_flush=time.monotonic()+1;stream.flush()
                        self._json('runtime_status.json',self.state)
                        self._json('summary.json',self._summary())
                stream.flush();self._json('runtime_status.json',self.state);self._json('summary.json',self._summary())
        except Exception as exc:self.error=str(exc)

    def close(self, wait=True):
        if self.halt.is_set():return
        self.event('runtime_closed');self.halt.set()
        (self.directory/'stop').touch()
        if wait:
            self.thread.join(timeout=5)
            if self.child:
                try:self.child.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
