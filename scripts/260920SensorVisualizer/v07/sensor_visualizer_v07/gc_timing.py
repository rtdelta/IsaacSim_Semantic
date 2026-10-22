"""Observe Python GC pauses; never change thresholds or disable collection."""
import gc
import threading
import time

class GCTiming:
    def __init__(self,diag):
        self.diag=diag;self.active={};self.counter=0;self.lock=threading.RLock();self.closed=False
        self.stats={str(gen):{'count':0,'wall_ns':0,'thread_cpu_ns':0,'max_ns':0,'collected':0,'uncollectable':0} for gen in range(3)}
        gc.callbacks.append(self.callback)
    def callback(self,phase,info):
        if self.closed:return
        generation=info['generation'];key=(threading.get_native_id(),generation)
        try:
            if phase=='start':
                with self.lock:
                    self.counter+=1;self.active[key]=(time.monotonic_ns(),time.thread_time_ns(),self.counter)
                    collection=self.counter
                if generation==2:self.diag.event('python_gc_begin',critical=True,generation=generation,collection_id=collection)
                return
            with self.lock:
                start=self.active.pop(key,None)
                if start is None:return
                wall=time.monotonic_ns()-start[0];cpu=time.thread_time_ns()-start[1]
                stats=self.stats[str(generation)];stats['count']+=1;stats['wall_ns']+=wall;stats['thread_cpu_ns']+=cpu
                stats['max_ns']=max(stats['max_ns'],wall)
                stats['collected']+=info.get('collected',0);stats['uncollectable']+=info.get('uncollectable',0)
            if generation==2 or wall>=self.diag.config['slow_stage_ms']*1_000_000:
                self.diag.event('python_gc_end',critical=True,generation=generation,collection_id=start[2],start_ns=start[0],
                    duration_ns=wall,thread_cpu_duration_ns=cpu,collected=info.get('collected'),uncollectable=info.get('uncollectable'),
                    timing_scope='Python GC callback interval; includes callback instrumentation overhead')
        except Exception:
            # GC observer failure cannot fail the collector or recursively log.
            with self.diag.lock:self.diag.dropped['gc_observer_error']+=1
    def snapshot(self):
        with self.lock:return {generation:dict(values) for generation,values in self.stats.items()}
    def close(self):
        self.closed=True
        try:gc.callbacks.remove(self.callback)
        except ValueError:pass
