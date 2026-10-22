"""Producer-side asynchronous IPC and process lifetime."""
import asyncio
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from .buffers import SlotPool, receive_message, send_message


class RecordPipeline:
    def __init__(self, project, session, job, registry, render, job_id):
        self.project, self.session, self.job = Path(project), Path(session), job
        self.registry, self.render, self.job_id = registry, render, job_id
        self.received = queue.Queue(); self.process = self.pool = self.conn = self.server = None
        self.finished = False; self.written = 0; self.ready = False; self.closing = False

    async def start(self):
        p = self.job['pipeline']
        self.control_dir = Path(tempfile.mkdtemp(prefix='sv02_'))
        os.chmod(self.control_dir,0o700)
        ram = Path('/dev/shm')
        parent = ram if ram.is_dir() and shutil.disk_usage(ram).free > p['slots']*p['slot_bytes']+64*1024**2 else self.session
        self.pool = SlotPool(parent/('sv02_buffers_'+self.job_id),p['slots'],p['slot_bytes'])
        path = self.control_dir/'control.sock'
        self.server = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.server.bind(str(path)); self.server.listen(1); self.server.settimeout(0.02)
        env = os.environ.copy()
        for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'): env.pop(name,None)
        env['PYTHONUNBUFFERED']='1'
        self.log = (self.session/'record_worker.log').open('ab')
        args = ['/bin/bash','--noprofile','--norc','-c',
                'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -u "$@"', 'sv02-record',
                str(self.project/'sensor_visualizer_v02/record_worker.py'),'--socket',str(path)]
        self.process = subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+p['timeout_s']
        while self.conn is None:
            if self.process.poll() is not None: raise RuntimeError('Record worker exited before connecting; see record_worker.log')
            if time.monotonic()>deadline: raise TimeoutError('Record worker startup timeout')
            try: self.conn,_ = self.server.accept()
            except socket.timeout: await asyncio.sleep(0.01)
        self.conn.settimeout(None)
        send_message(self.conn,{'protocol':2,'job':self.job,'registry':self.registry,'render':self.render,
                               'session':str(self.session),'job_id':self.job_id,'slot_directory':str(self.pool.directory)})
        self.thread = threading.Thread(target=self._reader,name='sv02-ipc-reader',daemon=True)
        self.thread.start()
        while not self.ready:
            self.poll()
            if time.monotonic()>deadline: raise TimeoutError('Record writer did not become ready')
            await asyncio.sleep(.01)

    def _reader(self):
        try:
            while not self.closing:
                message=receive_message(self.conn)
                self.received.put(message)
                if message.get('event') in ('finished','error'): return
        except Exception as exc:
            if not self.closing: self.received.put({'event':'error','error':str(exc)})

    def poll(self):
        while True:
            try: message=self.received.get_nowait()
            except queue.Empty: break
            event=message['event']
            if event=='release': self.pool.release(message['slot'],message['group_id'],message['generation'])
            elif event=='written': self.written=message['groups']
            elif event=='finished': self.finished=True; self.written=message['groups']
            elif event=='ready': self.ready=True
            elif event=='error': raise RuntimeError('Record worker: '+message['error'])
        if self.process and self.process.poll() is not None and not self.finished:
            raise RuntimeError('Record worker exited unexpectedly; see record_worker.log')

    async def reserve(self,group):
        deadline=time.monotonic()+self.job['pipeline']['timeout_s']
        while True:
            self.poll()
            slot=self.pool.reserve(group)
            if slot is not None: return slot
            if time.monotonic()>deadline: raise TimeoutError('Record buffer backpressure timeout')
            await asyncio.sleep(.01)

    def submit(self,slot,arrays,bundle):
        bundle['buffer']=self.pool.pack(slot,arrays)
        send_message(self.conn,{'event':'group','bundle':bundle})

    async def finish(self):
        self.poll()
        send_message(self.conn,{'event':'finish'})
        deadline=time.monotonic()+self.job['pipeline']['timeout_s']
        while not self.finished:
            self.poll()
            if time.monotonic()>deadline: raise TimeoutError('MCAP finalization timeout')
            await asyncio.sleep(.02)
        while self.process.poll() is None:
            if time.monotonic()>deadline: raise TimeoutError('Record worker cleanup timeout')
            await asyncio.sleep(.02)
        if self.process.returncode: raise RuntimeError('Record worker failed during cleanup')

    async def close(self):
        self.closing=True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            deadline=time.monotonic()+5
            while self.process.poll() is None and time.monotonic()<deadline: await asyncio.sleep(.05)
            if self.process.poll() is None: self.process.kill(); await asyncio.to_thread(self.process.wait)
        if self.conn:
            try: self.conn.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            self.conn.close()
        if hasattr(self,'thread'): self.thread.join(timeout=2)
        if self.server: self.server.close()
        if self.pool: self.pool.close()
        if hasattr(self,'log'): self.log.close()
        if hasattr(self,'control_dir'):
            (self.control_dir/'control.sock').unlink(missing_ok=True)
            self.control_dir.rmdir()
