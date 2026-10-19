"""Small owned messages; socket threads never access USD/Kit objects."""
from collections import deque
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import socket
import struct
import threading
import time
import uuid

MAX_BYTES=2*1024*1024
def _exact(conn,n):
    chunks=[]
    while n:
        chunk=conn.recv(n)
        if not chunk: raise EOFError('IPC disconnected')
        chunks.append(chunk); n-=len(chunk)
    return b''.join(chunks)
def receive(conn):
    n=struct.unpack('!I',_exact(conn,4))[0]
    if n>MAX_BYTES: raise ValueError('IPC message too large')
    return json.loads(_exact(conn,n))
def send(conn,value):
    data=json.dumps(value,allow_nan=False).encode()
    if len(data)>MAX_BYTES: raise ValueError('IPC message too large')
    conn.sendall(struct.pack('!I',len(data))+data)
def request(path,message,timeout=3):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout); conn.connect(str(path)); send(conn,message); return receive(conn)

class ControlEndpoint:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.commands=queue.Queue(256); self.receipts=deque(maxlen=512)
        self.lock=threading.Lock(); self.status={'phase':'initializing'}; self.closed=False
        if self.path.exists():
            try: request(self.path,{'action':'status'})
            except (OSError,EOFError): self.path.unlink()
            else: raise RuntimeError('Another control engine owns this socket')
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.server.bind(str(self.path)); os.chmod(self.path,0o600); self.server.listen(8); self.server.settimeout(.2)
        self.thread=threading.Thread(target=self._serve,name='s0602-control-ipc',daemon=True); self.thread.start()
    def publish(self,status):
        # Construct the immutable generation before acquiring the transport lock.
        owned=deepcopy(status)
        self.publish_owned(owned)
    def publish_owned(self,status):
        """Transfer a JSON generation; caller must never mutate reachable objects."""
        with self.lock: self.status=status
    def result(self,cmd,status,**extra):
        with self.lock: self.receipts.append({'command_id':cmd['command_id'],'action':cmd['action'],'state':status,
            'accepted_ns':cmd.get('accepted_ns'),'completed_ns':time.monotonic_ns(),**extra})
    def _serve(self):
        while not self.closed:
            try: conn,_=self.server.accept()
            except socket.timeout: continue
            except OSError: break
            with conn:
                conn.settimeout(2)
                try:
                    m=receive(conn)
                    if m['action'] in ('status','snapshot'):
                        with self.lock:
                            generation=self.status
                            receipts=list(self.receipts) if m['action']=='status' else None
                        # Serialization is on this thread, outside the owner lock.
                        if m['action']=='snapshot':
                            response={k:generation.get(k) for k in ('phase','session_id','heartbeat_ns','capture_snapshot')}
                        else:response={**generation,'receipts':receipts}
                    else:
                        m['command_id']=m.get('command_id') or uuid.uuid4().hex; m['accepted_ns']=time.monotonic_ns()
                        self.commands.put_nowait(m); response={'command_id':m['command_id'],'state':'queued'}
                    send(conn,response)
                except Exception as exc:
                    try: send(conn,{'state':'failed','error':str(exc)})
                    except OSError: pass
    def close(self):
        self.closed=True; self.server.close(); self.thread.join(timeout=3)
        self.path.unlink(missing_ok=True)
