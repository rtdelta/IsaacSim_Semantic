"""Bounded background logging keeps file writes outside Kit input callbacks."""
import json
import queue
import threading
import os
import time
import uuid
from datetime import datetime,timezone
from .contracts import write_json

class InteractionLog:
    def __init__(self,path,queue_size=4096):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.path=path;self.log_id=uuid.uuid4().hex;self.generated=0;self.written=0;self.peak=0
        self.queue=queue.Queue(queue_size);self.dropped=0;self.error=None;self.closed=False
        self.lock=threading.Lock();self.done=threading.Event();self.first_drop=None;self.last_drop=None
        self.file=path.open('a',encoding='utf-8');self.thread=threading.Thread(target=self._write,name='sv07-control-log',daemon=True)
        self.thread.start()
    def append(self,row):
        with self.lock:
            if self.closed:return
            self.generated+=1
            value={**row,'control_log_id':self.log_id,'control_event_seq':self.generated,
                   'logged_utc':datetime.now(timezone.utc).isoformat(),'logged_monotonic_ns':time.monotonic_ns()}
            try:self.queue.put_nowait(value);self.peak=max(self.peak,self.queue.qsize())
            except queue.Full:
                self.dropped+=1;self.first_drop=self.first_drop or self.generated;self.last_drop=self.generated
    def _write(self):
        try:
            while not self.closed or not self.queue.empty():
                try:row=self.queue.get(timeout=.1)
                except queue.Empty:continue
                try:
                    self.file.write(json.dumps(row,allow_nan=False)+'\n');self.written+=1
                    if self.queue.empty():self.file.flush()
                except Exception as exc:self.error=str(exc)
                finally:self.queue.task_done()
            self.file.flush();os.fsync(self.file.fileno())
        except Exception as exc:self.error=str(exc)
        finally:
            self.file.close()
            summary={'log_id':self.log_id,'events_generated':self.generated,'events_written':self.written,
                     'dropped':self.dropped,'first_dropped_seq':self.first_drop,'last_dropped_seq':self.last_drop,
                     'queue_peak':self.peak,'io_error':self.error,'closed_utc':datetime.now(timezone.utc).isoformat(),
                     'complete':self.error is None and self.dropped==0 and self.generated==self.written}
            try:
                write_json(self.path.with_name(self.path.stem+'.'+self.log_id+'.summary.json'),summary)
                write_json(self.path.with_suffix('.summary.json'),summary)
            except Exception as exc:self.error=str(exc)
            self.done.set()
    def close(self):
        with self.lock:self.closed=True
        self.thread.join(timeout=5)
        if not self.done.is_set():self.error='Control log drain has not completed after 5 seconds'
