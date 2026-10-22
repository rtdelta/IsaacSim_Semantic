"""Instrument the frozen runtime, retaining the SDK's original synchronization.

Cross-await spans measure host wall time, not exclusive CPU or GPU execution.
No SDK pointer is retained or copied on another stream by this observer.
"""
import hashlib
import inspect
import json
import time
from pathlib import Path
from contextlib import contextmanager


WAITS = {
 'SceneStepper.advance_clock': ('Kit application updates', 'native simulation clock', 'await next_update_async + grid check'),
 'SensorDrivers._native': ('Replicator operation', 'single inflight task', 'shielded asyncio task completion; cancellation drains'),
 'SensorDrivers._step': ('Replicator / RTX', 'render generation', 'step_async returned with wait_for_render=True'),
 'SensorDrivers._drain_generation': ('Replicator', 'render generation', 'wait_until_complete_async returned; generation stopped'),
 'SensorDrivers.acquire': ('manual snapshot writers', 'request-bound sensor payloads', 'all callbacks + source time / pose validation'),
 'SensorDrivers._copy_host': ('Warp / SDK', 'source array', '.numpy or asarray returned; implicit synchronization possible'),
 'RecordPipeline.reserve': ('record worker', 'mmap slot + generation', 'matching slot release receipt'),
 'RecordPipeline.submit': ('packing thread', 'owned CPU arrays / mmap slot', 'pack/send thread returned; writer completion separate'),
 'RecordPipeline.finish': ('record worker', 'MCAP', 'finished receipt'),
}


def brief_array(value):
    """Metadata inspection only; never call numpy(), materialize or repr(array)."""
    device=getattr(value,'device',None)
    ptr=getattr(value,'ptr',None)
    try: shape=list(value.shape)
    except Exception: shape=None
    return {'type':type(value).__module__+'.'+type(value).__name__,
            'shape':shape,'device':str(device) if device is not None else 'not_exposed',
            'buffer_fingerprint':hashlib.sha256(str(ptr).encode()).hexdigest()[:16] if ptr else None,
            'lifetime':'only observed inside callback; no SDK retention guarantee',
            'producer_fence':'not exposed by this payload; step return and writer receipt retained'}


class Probe:
    def __init__(self,spec):
        self.spec=spec;self.restore=[];self.window=None;self.native=None
        self.target=spec.get('trace_window','none')
        self.selected_group=spec.get('trace_group',1)

    def mark(self,diag,label,**fields):
        host=time.monotonic_ns()
        diag.event('lab_clock_anchor',critical=True,label=label,host_monotonic_ns=host,**fields)
        if diag.native_trace:
            self.native=diag.native_trace
            zone=self.native.begin('SL06_SYNC host_ns='+str(host)+' '+label)
            self.native.end(zone)

    def start_window(self,diag,name):
        if self.target!=name or self.window is not None:return False
        # Cross-thread NVTX range IDs are safe across await. Nsight triggers on
        # this exact range name; the inclusive interval is not exclusive CPU.
        if not diag.native_trace:raise RuntimeError('NVTX unavailable for selected native window')
        # Own-process maps, selected runtime modules only. Used with installed
        # ELF dynamic symbols to resolve public API frames without binary hooks.
        if Path('/proc/self/maps').is_file():
            for line in Path('/proc/self/maps').read_text().splitlines():
                fields=line.split(maxsplit=5)
                if len(fields)==6 and any(k in fields[5] for k in ('libnvrtc','libcuda.so','libgpu.foundation','librtx.sensors')):
                    lo,hi=fields[0].split('-')
                    diag.event('lab_module_mapping',critical=True,module=fields[5],start_address=int(lo,16),
                               end_address=int(hi,16),file_offset=int(fields[2],16),permissions=fields[1])
        self.mark(diag,'window_start',window=name)
        started=time.monotonic_ns()
        self.window=diag.native_trace.begin('SL06_WINDOW')
        diag.event('lab_profile_window',critical=True,action='begin',window=name,
                   trigger_call_wall_ns=time.monotonic_ns()-started,
                   limit='profiler trigger may block; excluded from inner experiment scopes')
        return True

    def end_window(self,diag,selected):
        if not selected:return
        started=time.monotonic_ns();diag.native_trace.end(self.window);self.window=None
        self.mark(diag,'window_end',window=self.target)
        diag.event('lab_profile_window',critical=True,action='end',window=self.target,
                   trigger_call_wall_ns=time.monotonic_ns()-started,
                   limit='profiler range end/export may block; never treated as ordinary throughput')

    def install(self):
        from sensor_visualizer_v06.scene import SceneStepper
        from sensor_visualizer_v06.sensors import SensorDrivers
        from sensor_visualizer_v06.pipeline import RecordPipeline
        from sensor_visualizer_v06.gating import ProductGate
        for cls,names in ((SceneStepper,('initialize','advance_clock','apply_snapshot','capture','close')),
                          (SensorDrivers,('_native','_step','warm_cameras','_drain_generation',
                                          'acquire','_copy_host','_receive','detach','destroy')),
                          (RecordPipeline,('start','reserve','submit','finish','close')),
                          (ProductGate,('add','set'))):
            for name in names:self.wrap(cls,name)

    def wrap(self,cls,name):
        original=getattr(cls,name);key=cls.__name__+'.'+name;probe=self

        def begin(obj,args,kwargs):
            diag=obj.diag;fields={'api':key,'resource_policy':getattr(obj,'resource_policy',None)}
            selected=False
            if key=='RecordPipeline.reserve':
                diag.context(group_id=args[0],phase='group_preparation',request_id=None,attempt_id=None,
                             sensor_id=None,simulation_time_ns=None)
            if key=='SceneStepper.advance_clock' and probe.spec.get('full_group_window',False) and diag.ctx.get('group_id')==probe.selected_group:
                probe.start_window(diag,'steady')
            if key=='SceneStepper.initialize':selected=probe.start_window(diag,'initialize')
            if key=='SceneStepper.close':selected=probe.start_window(diag,'cleanup')
            if key=='SceneStepper.capture':
                diag.context(group_id=args[0],simulation_time_ns=args[1]);fields['group_id']=args[0]
                if args[0]==probe.selected_group and not probe.spec.get('full_group_window',False):selected=probe.start_window(diag,'steady')
                probe.mark(diag,'group_start',group_id=args[0])
            if key=='SensorDrivers._copy_host':
                fields.update(source_buffer=brief_array(args[0]),sensor_id=args[1])
                diag.event('lab_source_buffer',critical=True,**fields)
            if key=='ProductGate.add':fields['sensor_id']=args[0]
            span=diag.begin('lab.'+key,**fields)
            if key in WAITS:
                producer,resource,signal=WAITS[key]
                diag.event('lab_dependency',critical=True,waiter=key,producer=producer,
                    resource=resource,completion_signal=signal,dependency_span_id=span['span_id'],
                    classification='host inclusive scope; duration is not pure wait',
                    release_conditions='original runtime checks preserved',**fields)
            return diag,span,selected

        def end(obj,args,diag,span,selected,status):
            try:
                if key=='ProductGate.add':diag.event('lab_resource_created',critical=True,sensor_id=args[0],resource='render_product')
                if key=='SensorDrivers.destroy':diag.event('lab_resource_destroyed',critical=True,resource='all owned render_products')
                if key=='SceneStepper.capture':probe.mark(diag,'group_end',group_id=args[0])
                diag.end(span,status=status)
            finally:
                if key=='RecordPipeline.submit' and probe.spec.get('full_group_window',False) and diag.ctx.get('group_id')==probe.selected_group and probe.window is not None:
                    selected=True
                probe.end_window(diag,selected)

        if inspect.iscoroutinefunction(original):
            async def wrapped(obj,*args,**kwargs):
                diag,span,selected=begin(obj,args,kwargs);status='failed'
                try:
                    result=await original(obj,*args,**kwargs);status='ok';return result
                finally:end(obj,args,diag,span,selected,status)
        else:
            def wrapped(obj,*args,**kwargs):
                diag,span,selected=begin(obj,args,kwargs);status='failed'
                try:
                    result=original(obj,*args,**kwargs);status='ok';return result
                finally:end(obj,args,diag,span,selected,status)
        setattr(cls,name,wrapped);self.restore.append((cls,name,original))

    def uninstall(self):
        for cls,name,original in reversed(self.restore):setattr(cls,name,original)
        self.restore=[]
