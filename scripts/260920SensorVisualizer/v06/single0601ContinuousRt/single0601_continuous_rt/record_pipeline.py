"""Nonblocking owner IPC to one separate CPU ROS/MCAP process."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from .common import cjson, save_json, ContractError


def cpu_environment():
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):
        env.pop(key,None)
    return env


class RecordPipeline:
    def __init__(self, project, session, hello):
        self.session, self.project = Path(session), Path(project)
        hello_path = self.session/'worker_hello.json'
        save_json(hello_path, hello)
        self.send_queue = queue.Queue(maxsize=hello['job']['pipeline']['encoded_queue_groups'])
        self.ack_queue = queue.Queue(maxsize=16)
        self.error = None
        self.stderr = (self.session/'logs/worker_stderr.log').open('wb')
        self.console = (self.session/'logs/worker_console.log').open('wb')
        command = ['/bin/bash', '-c', 'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B -m single0601_continuous_rt.record_worker --hello "$1"',
                   'single0601-worker', str(hello_path)]
        self.process = subprocess.Popen(command, cwd=self.project, env=cpu_environment(),stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr, bufsize=0)
        self.reader = threading.Thread(target=self._read, daemon=True, name='s0601-worker-acks')
        self.sender = threading.Thread(target=self._send, daemon=True, name='s0601-worker-input')
        self.reader.start()
        self.sender.start()

    def _send(self):
        try:
            while True:
                value = self.send_queue.get()
                if value is None:
                    self.process.stdin.close()
                    return
                block = memoryview(cjson(value)+b'\n')
                while block:
                    n = self.process.stdin.write(block)
                    if not n:
                        raise BrokenPipeError('Worker pipe closed')
                    block = block[n:]
        except Exception as exc:
            self.error = {'code': 'worker_ipc', 'message': str(exc)}

    def _read(self):
        try:
            for raw in self.process.stdout:
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeError):
                    self.console.write(raw)
                    continue
                self.ack_queue.put(value, timeout=10)
        except Exception as exc:
            self.error = {'code': 'worker_ack', 'message': str(exc)}

    def send(self, value):
        if self.error:
            raise ContractError(self.error['code'], self.error['message'])
        if self.process.poll() is not None:
            raise ContractError('worker_died', 'CPU worker exited with code %s' % self.process.returncode)
        try:
            self.send_queue.put_nowait(value)
        except queue.Full:
            raise ContractError('reserved_queue_full', 'Reserved input capacity was exhausted; recording must fail')

    def poll(self):
        if self.error:
            raise ContractError(self.error['code'], self.error['message'])
        items = []
        while True:
            try:
                items.append(self.ack_queue.get_nowait())
            except queue.Empty:
                break
        return items

    def close_resources(self):
        if self.process.poll() is None:
            raise ContractError('worker_not_closed', 'Worker must exit after segment close before IPC cleanup')
        self.send_queue.put_nowait(None)
        self.stderr.close()
        self.console.close()
