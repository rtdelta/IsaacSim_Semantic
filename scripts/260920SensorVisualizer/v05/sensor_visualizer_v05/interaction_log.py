"""Bounded background logging keeps file writes outside Kit input callbacks."""
import json
import queue
import threading

class InteractionLog:
    def __init__(self,path):
        self.queue=queue.Queue(4096);self.dropped=0;self.error=None;self.closed=False
        self.file=path.open('a',encoding='utf-8');self.thread=threading.Thread(target=self._write,name='sv05-control-log',daemon=True)
        self.thread.start()
    def append(self,row):
        if self.closed:return
        try:self.queue.put_nowait(row)
        except queue.Full:self.dropped+=1
    def _write(self):
        while True:
            row=self.queue.get()
            try:
                if row is None:return
                self.file.write(json.dumps(row,allow_nan=False)+'\n')
                if self.queue.empty():self.file.flush()
            except Exception as exc:self.error=str(exc)
            finally:self.queue.task_done()
    def close(self):
        if self.closed:return
        self.closed=True;self.queue.put(None);self.thread.join();self.file.close()
