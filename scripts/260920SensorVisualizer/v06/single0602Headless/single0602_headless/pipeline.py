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
from .diagnostics import NullDiagnostics


class RecordPipeline:
    def __init__(self, project, session, job, registry, render, job_id, diagnostics=None):
        self.diag=diagnostics or NullDiagnostics(); self.finishing=False
        self.project, self.session, self.job = Path(project), Path(session), job
        self.registry, self.render, self.job_id = registry, render, job_id
        self.received = queue.Queue(); self.process = self.pool = self.conn = self.server = None
        self.finished = False; self.written = 0; self.ready = False; self.closing = False

    async def start(self):
        p = self.job['pipeline']
        self.control_dir = Path(tempfile.mkdtemp(prefix='s0602_'))
        os.chmod(self.control_dir,0o700)
        ram = Path('/dev/shm')
        parent = ram if ram.is_dir() and shutil.disk_usage(ram).free > p['slots']*p['slot_bytes']+64*1024**2 else self.session
        self.pool = SlotPool(parent/('s0602_buffers_'+self.job_id),p['slots'],p['slot_bytes'])
        path = self.control_dir/'control.sock'
        self.server = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.server.bind(str(path)); self.server.listen(1); self.server.settimeout(0.02)
        env = os.environ.copy()
        for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'): env.pop(name,None)
        env['PYTHONUNBUFFERED']='1'
        self.log = (self.session/'record_worker.log').open('ab')
        args = ['/bin/bash','--noprofile','--norc','-c',
                'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -u "$@"', 's0602-record',
                str(self.project/'single0602_headless/record_worker.py'),'--socket',str(path)]
        self.process = subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+p['timeout_s']
        while self.conn is None:
            if self.process.poll() is not None: raise RuntimeError('Record worker exited before connecting; see record_worker.log')
            if time.monotonic()>deadline: raise TimeoutError('Record worker startup timeout')
            try: self.conn,_ = self.server.accept()
            except socket.timeout: await asyncio.sleep(0.01)
        # Receive must remain valid during arbitrarily long user pauses.
        self.conn.settimeout(None)
        await self._io(send_message,self.conn,{'protocol':3,'job':self.job,'registry':self.registry,'render':self.render,
                               'session':str(self.session),'job_id':self.job_id,'slot_directory':str(self.pool.directory),
                               'run_id':self.diag.run_id,'diagnostics_directory':str(self.diag.directory)})
        self.thread = threading.Thread(target=self._reader,name='s0602-ipc-reader',daemon=True)
        self.thread.start()
        while not self.ready:
            self.poll()
            if time.monotonic()>deadline: raise TimeoutError('Record writer did not become ready')
            await asyncio.sleep(.01)

    def _reader(self):
        try:
            while not self.closing:
                message=receive_message(self.conn)
                self.diag.event('ipc_received',message_type=message.get('event'),group_id=message.get('group_id'),capture_id=self.job_id)
                self.received.put(message)
                if message.get('event') in ('finished','error'): return
        except Exception as exc:
            if not self.closing: self.received.put({'event':'error','error':str(exc)})

    def poll(self):
        while True:
            try: message=self.received.get_nowait()
            except queue.Empty: break
            event=message['event']
            if event=='release':
                if message.get('capture_id')!=self.job_id: raise RuntimeError('Wrong capture release')
                self.pool.release(message['slot'],message['group_id'],message['generation'])
                self.diag.event('slot_released',slot_id=message['slot'],slot_generation=message['generation'],group_id=message['group_id'],capture_id=self.job_id)
            elif event=='written': self.written=message['groups']
            elif event=='finished': self.finished=True; self.written=message['groups']
            elif event=='ready': self.ready=True
            elif event=='error': raise RuntimeError('Record worker: '+message['error'])
        if self.process and self.process.poll() is not None and not self.finished:
            raise RuntimeError('Record worker exited unexpectedly; see record_worker.log')

    async def reserve(self,group,cancel=None):
        deadline=time.monotonic()+self.job['pipeline']['timeout_s']
        while True:
            self.poll()
            if cancel and cancel(): return None
            slot=self.pool.reserve(group)
            if slot is not None:
                self.diag.event('slot_reserved',slot_id=slot,slot_generation=self.pool.generations[slot],group_id=group,in_use=len(self.pool.in_use))
                return slot
            if time.monotonic()>deadline: raise TimeoutError('buffer_wait_timeout: Record buffer backpressure timeout')
            await asyncio.sleep(.01)

    async def submit(self,slot,arrays,bundle):
        # Only owned CPU arrays cross to this thread. No USD/Kit/annotator calls.
        for value in arrays.values(): value.flags.writeable=False
        self.pool.claim_owned(slot)
        self.diag.event('slot_capture_owned',slot_id=slot,group_id=bundle['group_id'])
        def pack_send():
            with self.diag.span('slot_pack',slot_id=slot,group_id=bundle['group_id']):
                bundle['buffer']=self.pool.pack(slot,arrays)
            self.diag.event('slot_packed',slot_id=slot,group_id=bundle['group_id'],bytes=bundle['buffer']['used_bytes'])
            with self.diag.span('ipc_send',group_id=bundle['group_id']):
                self.pool.mark_sent(slot)
                send_message(self.conn,{'event':'group','bundle':bundle})
            self.diag.event('slot_sent',slot_id=slot,group_id=bundle['group_id'])
        await self._io(pack_send)

    async def _io(self,fn,*args):
        task=asyncio.create_task(asyncio.to_thread(fn,*args))
        try: return await asyncio.wait_for(asyncio.shield(task),self.job['pipeline']['timeout_s'])
        except asyncio.TimeoutError:
            if self.conn:
                try:self.conn.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            await asyncio.gather(task,return_exceptions=True)
            raise TimeoutError('Writer IPC send/pack timeout; connection closed')
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise

    async def finish(self):
        self.poll()
        if self.finished: return
        if not self.finishing:
            self.finishing=True
            await self._io(send_message,self.conn,{'event':'finish'})
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
        if hasattr(self,'thread'): await asyncio.to_thread(self.thread.join,2)
        if self.server: self.server.close()
        if self.pool: self.pool.close()
        if hasattr(self,'log'): self.log.close()
        if hasattr(self,'control_dir'):
            (self.control_dir/'control.sock').unlink(missing_ok=True)
            self.control_dir.rmdir()
