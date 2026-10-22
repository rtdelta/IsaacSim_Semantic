"""Bounded, process-local tracing. No image data or environment dump is logged."""
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import queue
import re
import threading
import time
import uuid
from .contracts import write_json


def redact(text):
    text = re.sub(r'(?i)(password|passwd|token|secret|authorization)(\s*[:=]\s*)\S+', r'\1\2[redacted]', str(text))
    text = re.sub(r'(https?://)[^/\s@]+@', r'\1[redacted]@', text)
    return text[:4000]


class NullDiagnostics:
    run_id = None
    directory = None
    def event(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def context(self, **kwargs): pass
    def begin(self, *args, **kwargs): return None
    def end(self, *args, **kwargs): pass
    def set_manifest(self, **kwargs): pass
    @contextmanager
    def span(self, *args, **kwargs): yield None


class RunDiagnostics:
    def __init__(self, output, config, project=None, role='isaac', run_id=None, directory=None):
        self.run_id = run_id or (datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:8])
        self.directory = Path(directory) if directory else Path(output)/'runs'/self.run_id/'diagnostics'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.role, self.config = role, dict(config)
        self.pid = os.getpid(); self.started = time.monotonic_ns()
        self.lock = threading.RLock(); self.ctx = {}; self.seq = 0
        self.queue = queue.Queue(maxsize=config['event_queue_capacity'])
        self.critical = queue.Queue(maxsize=max(32, config['event_queue_capacity']//8))
        self.dropped = Counter(); self.counts = Counter(); self.warnings = {}
        self.spans = defaultdict(lambda: {'count':0, 'total_ns':0, 'max_ns':0, 'recent_ns':deque(maxlen=2048)})
        self.ring = deque(maxlen=config['event_queue_capacity'])
        self.stop = threading.Event(); self.closed = False; self.io_error = None
        self.anomalies=queue.Queue(maxsize=2); self.last_anomaly=0
        self.profiler=None
        self.manifest = {'schema_version':3, 'run_id':self.run_id, 'state':'incomplete',
            'started_utc':datetime.now(timezone.utc).isoformat(), 'diagnostics':config,
            'clock':'same-host monotonic_ns; UTC for humans; simulation clock independent',
            'timing_limit':'Host spans include native/GPU waits. Nanosecond units do not imply nanosecond accuracy.',
            'scene_load_before_run':'unobserved', 'capabilities':{}}
        if project:
            root = Path(project)
            self.manifest['code_sha256'] = {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*.py') if not any(part in ('__pycache__','generated','reports','deploy_history')
                                                     for part in p.relative_to(root).parts)}
        if config['native_profiler']=='markers':
            try:
                import carb.profiler
                self.profiler=carb.profiler
                self.manifest['native_profiler']='paired immediate begin/end markers; async durations in JSONL'
            except ImportError: self.manifest['native_profiler']='unavailable'
        else: self.manifest['native_profiler']='off'
        self.thread = threading.Thread(target=self._write, name='sv03-trace-'+role, daemon=True)
        self.thread.start()
        self.event('run_opened', critical=True)
        self.sampler = None; self.kit_subscription = None; self.log_subscription = None

    def context(self, **values):
        with self.lock: self.ctx.update(values)

    def set_manifest(self, **values):
        with self.lock: self.manifest.update(values)
        self.event('manifest_changed')

    def event(self, event, critical=False, detail=False, **values):
        if self.closed: return
        with self.lock:
            if self.io_error:
                self.dropped['io_error']+=1; return
            group = values.get('group_id', self.ctx.get('group_id'))
            selected = self.config.get('detail_group_range')
            detailed = self.config['level'] != 'basic' and (selected is None or group is not None and selected[0] <= group <= selected[1])
            if detail and not detailed: return
            self.seq += 1
            row = {'schema_version':3, 'run_id':self.run_id, 'pid':self.pid, 'tid':threading.get_native_id(),
                'process_role':self.role, 'event_seq':self.seq, 'event':event,
                'monotonic_ns':time.monotonic_ns(), 'utc':datetime.now(timezone.utc).isoformat(),
                'measurement_source':'host', 'status':'ok', 'capture_id':None, 'group_id':None,
                'request_id':None, 'attempt_id':None, 'stage_generation':None, 'sensor_id':None,
                'simulation_time_ns':None, 'source_simulation_time_ns':None, 'source_frame_id':None,
                **self.ctx, **values}
            # Only small, caller-owned JSON metadata is accepted; never ndarray/repr.
            self.counts[event] += 1
            self.ring.append(row)
            cutoff = row['monotonic_ns']-int(self.config['ring_history_seconds']*1e9)
            while self.ring and self.ring[0]['monotonic_ns'] < cutoff: self.ring.popleft()
            try: (self.critical if critical else self.queue).put_nowait(row)
            except queue.Full: self.dropped['critical' if critical else 'normal'] += 1
            if event in ('slow_stage','failure','capture_retry','warning') and row['monotonic_ns']-self.last_anomaly>5_000_000_000:
                self.last_anomaly=row['monotonic_ns']
                try: self.anomalies.put_nowait((self.seq,list(self.ring)))
                except queue.Full: self.dropped['anomaly_history']+=1

    def _marker(self,label):
        if self.profiler is None:return
        try:
            self.profiler.begin(1,label); self.profiler.end(1)
        except Exception:
            self.profiler=None; self.set_manifest(native_profiler='marker API failed; JSONL continues')

    def begin(self, name, parent_span_id=None, **values):
        span = {'span_id':uuid.uuid4().hex, 'name':name, 'start_ns':time.monotonic_ns(),
                'parent_span_id':parent_span_id, **values}
        self.event('span_begin', **span)
        self._marker('SV03 begin '+name+' '+span['span_id'])
        return span

    def end(self, span, status='ok', **values):
        if span is None: return
        duration = time.monotonic_ns()-span['start_ns']
        with self.lock:
            row = self.spans[span['name']]; row['count'] += 1; row['total_ns'] += duration
            row['max_ns'] = max(row['max_ns'], duration); row['recent_ns'].append(duration)
        self.event('span_end', **span, duration_ns=duration, status=status, **values)
        self._marker('SV03 end '+span['name']+' '+span['span_id'])
        if duration > self.config['slow_stage_ms']*1e6:
            self.event('slow_stage', critical=True, name=span['name'], duration_ns=duration, span_id=span['span_id'])

    @contextmanager
    def span(self, name, **values):
        # Explicit IDs also work across await: never hold a native thread zone open.
        span = self.begin(name, **values)
        try: yield span
        except BaseException as exc:
            self.end(span, status='failed', error=redact(exc)); raise
        else: self.end(span)

    def warning(self, code, message, association='direct', **values):
        message = redact(message)
        key = code+':'+message
        now = time.monotonic_ns()
        with self.lock:
            if key not in self.warnings and len(self.warnings)>=1024:
                key='warning_unique_overflow'; code=key; message='Additional unique warnings aggregated; original Kit log retained'
                self.dropped['warning_unique']+=1
            row = self.warnings.setdefault(key, {'code':code, 'sample':message, 'count':0,
                'first_ns':now, 'last_ns':now, 'association':association})
            row['count'] += 1; row['last_ns'] = now
            count = row['count']
        # Powers of two preserve warning storms without repeating every text line.
        if count == 1 or count & (count-1) == 0:
            self.event('warning', critical=True, code=code, message=message, count=count,
                       association=association, **values)

    def attach_kit(self, app):
        last = [time.monotonic_ns()]
        def update(_):
            now = time.monotonic_ns(); delta = now-last[0]; last[0] = now
            if delta >= self.config['slow_stage_ms']*1e6:
                self.event('kit_update_gap', interval_ns=delta, measurement_source='kit_update_event')
        self.kit_subscription = app.get_update_event_stream().create_subscription_to_pop(update, name='SV03 update timing')
        try:
            import carb.settings
            self.set_manifest(kit_log_path=carb.settings.get_settings().get('/log/file'))
            import omni.log
            def on_message(channel,level,module,file,function,line,message,pid,tid,timestamp):
                # No calls back into omni.log (or any native logger) here.
                if int(level)>=int(omni.log.Level.WARN):
                    self.warning('kit_warning',message,association='time_inferred',channel=str(channel),
                                 measurement_source='omni.log',native_log_pid=pid,native_log_tid=tid,
                                 native_log_timestamp=timestamp)
            self.log_interface = omni.log.get_log()
            self.log_subscription = self.log_interface.add_message_consumer(on_message)
            self.set_manifest(warning_capture='omni.log consumer; original log retained')
        except Exception as exc:
            self.set_manifest(warning_capture='unavailable; inspect original Kit log', warning_capture_error=redact(exc))

    def start_resources(self):
        if self.sampler is None:
            from .resources import ResourceSampler
            self.sampler = ResourceSampler(self)

    def _snapshot(self, state):
        with self.lock:
            spans = {k:{'count':v['count'], 'total_ns':v['total_ns'], 'max_ns':v['max_ns'],
                'recent_p95_ns':sorted(v['recent_ns'])[min(len(v['recent_ns'])-1,int(len(v['recent_ns'])*.95))]}
                for k,v in self.spans.items()}
            return {'schema_version':3, 'state':state, 'run_id':self.run_id, 'role':self.role,
                'spans':spans, 'events':dict(self.counts), 'telemetry_dropped':dict(self.dropped),
                'io_error':self.io_error, 'wall_ns':time.monotonic_ns()-self.started}

    def _checkpoint(self, state):
        suffix = '' if self.role == 'isaac' else '_'+self.role+'_'+str(self.pid)
        write_json(self.directory/('summary'+suffix+'.json'), self._snapshot(state))
        with self.lock:
            warnings = list(self.warnings.values()); manifest = dict(self.manifest)
        write_json(self.directory/('warnings'+suffix+'.json'), warnings)
        if self.role == 'isaac': write_json(self.directory/'manifest.json', {**manifest, 'state':state})

    def _write(self):
        streams = {}; last = 0
        try:
            streams['events'] = (self.directory/f'events_{self.role}_{self.pid}.jsonl').open('a', encoding='utf-8')
            for kind in ('resources', 'warnings'):
                streams[kind] = (self.directory/f'{kind}_{self.role}_{self.pid}.jsonl').open('a', encoding='utf-8')
            anomaly_index=0
            while not self.stop.is_set() or not self.queue.empty() or not self.critical.empty() or not self.anomalies.empty():
                rows = []
                for q in (self.critical, self.queue):
                    for _ in range(512):
                        try: rows.append(q.get_nowait())
                        except queue.Empty: break
                for row in rows:
                    dest = 'resources' if row['event']=='resource_sample' else 'warnings' if row['event']=='warning' else 'events'
                    streams[dest].write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
                for stream in streams.values(): stream.flush()
                try:
                    seq,history=self.anomalies.get_nowait()
                    path=self.directory/f'anomaly_{self.role}_{self.pid}_{anomaly_index%32:02d}.jsonl'
                    with path.open('w',encoding='utf-8') as stream:
                        for row in history:stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                    anomaly_index+=1
                except queue.Empty:pass
                if time.monotonic()-last >= 2:
                    self._checkpoint('incomplete'); last = time.monotonic()
                if not rows: self.stop.wait(self.config['flush_interval_ms']/1000)
            self._checkpoint('closed')
        except Exception as exc:
            # Logging failure must not recursively log, block rendering or eat RAM.
            self.io_error = redact(exc)
        finally:
            for stream in streams.values():
                try: stream.close()
                except OSError: pass

    def detach_kit(self):
        """Call on the Kit owner thread, before handing file drain to a thread."""
        self.kit_subscription = None
        if self.log_subscription:
            try: self.log_interface.remove_message_consumer(self.log_subscription)
            except Exception: pass
            self.log_subscription = None

    def close(self):
        if self.closed: return
        self.event('run_closed', critical=True)
        if self.sampler: self.sampler.close()
        self.closed = True; self.stop.set(); self.thread.join(timeout=5)
        if not self.thread.is_alive():
            try: self._checkpoint('closed' if not self.io_error else 'logging_failed')
            except OSError: pass
            if self.config['export_trace_on_stop'] and self.role=='isaac' and not self.io_error:
                try:
                    from .analysis import analyze
                    analyze(self.directory,export_trace=True)
                except Exception as exc:
                    self.io_error=redact(exc)


class CaptureTelemetry:
    """Compatibility counters; event writes use the run's nonblocking writer."""
    def __init__(self, directory, diagnostics):
        self.directory=Path(directory); self.diag=diagnostics; self.phase='initializing'; self.group=-1
        self.pids = diagnostics.sampler.pids if diagnostics.sampler else {}
        self.rows=defaultdict(lambda: {'count':0,'total_s':0.,'samples':deque(maxlen=4096)})
    def event(self, event, **values): self.diag.event(event, **values)
    def measure(self, name, duration, **values):
        row=self.rows[name]; row['count']+=1; row['total_s']+=duration; row['samples'].append(duration)
        self.diag.event('capture_timing', name=name, duration_ns=round(duration*1e9), **values)
    def close(self):
        write_json(self.directory/'summary.json', {'spans':{k:{'count':v['count'],'total_s':v['total_s'],
            'mean_s':v['total_s']/v['count']} for k,v in self.rows.items()},
            'events_directory':str(self.diag.directory), 'format':'v03 per-process events replace synchronous timings.jsonl'})
