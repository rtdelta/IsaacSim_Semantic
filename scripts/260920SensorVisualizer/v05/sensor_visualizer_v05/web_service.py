"""Zero-download loopback HTTP backend; optional ASGI wrapper uses the same service."""
import io
import csv
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from .control_ipc import request
from .capture_supervisor import CaptureSupervisor
from .trajectory import Trajectory

class WebService:
    def __init__(self,project,output,socket_path):
        self.project,self.output,self.socket=Path(project),Path(output),Path(socket_path)
        self.output.mkdir(parents=True,exist_ok=True);self.token=secrets.token_urlsafe(24)
        self.engine={'phase':'disconnected'};self.lock=threading.Lock();self.closed=False
        self.supervisor=CaptureSupervisor(project,output,socket_path)
        self.thread=threading.Thread(target=self._poll,name='sv05-web-state',daemon=True);self.thread.start()
    def _poll(self):
        while not self.closed:
            try:
                s=request(self.socket,{'action':'status'},timeout=.4)
                s['stale']=time.monotonic_ns()-s.get('heartbeat_ns',0)>2_000_000_000
            except Exception as exc:s={'phase':'disconnected','error':str(exc)}
            with self.lock:self.engine=s
            time.sleep(.1)
    def status(self):
        with self.lock:engine=self.engine.copy()
        trajectories=[]
        for parent in ('trajectories','imports'):
            for p in sorted((self.output/parent).glob('*/metadata.json'),reverse=True)[:100]:
                try:
                    meta=json.loads(p.read_text());trajectories.append({'path':str(p.parent),'rows':meta.get('rows'),
                        'complete':meta.get('recording_complete',True),'error':meta.get('error')})
                except (OSError,json.JSONDecodeError):pass
        return {'engine':engine,'tasks':self.supervisor.status(),'trajectories':trajectories,'transport':'stdlib_http_polling',
                'dependencies_downloaded':False}
    def command(self,m):
        if m.get('action') not in {'keys','keyboard','play','pause','motion','hold','mount','save_mounts','reset_mounts','record_start','record_stop','reset','stop','exit','reinitialize','close'}:
            raise ValueError('Unsupported control action')
        if m.get('action') in ('stop','reset','exit','close') and any(x['running'] for x in self.supervisor.status()):
            raise ValueError('Stop + Drain capture and wait for process exit before restoring or exiting the controller')
        return request(self.socket,m)
    def import_trajectory(self,data):
        metadata=data['metadata']
        trajectory=Trajectory.from_csv(data['csv'],metadata) if 'csv' in data else Trajectory(data['states'],metadata)
        metadata.update(recording_complete=True,rows=len(trajectory.states),joint_names=sorted(trajectory.states[0]['joints_deg']))
        revisions={str(x['mount_revision']):x['mounts'] for x in trajectory.states};metadata['mount_revisions']=revisions
        directory=self.output/'imports'/uuid.uuid4().hex;directory.mkdir(parents=True)
        (directory/'metadata.json').write_text(json.dumps(metadata,allow_nan=False),encoding='utf-8')
        with (directory/'states.jsonl').open('w',encoding='utf-8') as f:
            for row in trajectory.states:f.write(json.dumps(row,allow_nan=False)+'\n')
        names=metadata['joint_names']
        with (directory/'trajectory.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.writer(f);writer.writerow(['seq','t_sim_s','state_revision','mount_revision','transition_kind',
                'base_x_m','base_y_m','base_z_m','base_qx','base_qy','base_qz','base_qw']+['joint_'+n+'_deg' for n in names])
            for i,row in enumerate(trajectory.states):writer.writerow([i,row['t_sim_s'],row['state_revision'],row['mount_revision'],row.get('transition_kind','continuous'),
                *row['position_world_m'],*row['quaternion_xyzw'],*[row['joints_deg'][n] for n in names]])
        return {'path':str(directory),'rows':len(trajectory.states),'duration_s':trajectory.duration}
    def import_zip(self,data):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=set(z.namelist())
            if not {'trajectory.csv','metadata.json'}<=names:raise ValueError('ZIP needs trajectory.csv and metadata.json at root')
            if sum(x.file_size for x in z.infolist())>256*1024**2:raise ValueError('Uncompressed trajectory exceeds 256 MiB')
            metadata=json.loads(z.read('metadata.json'));text=z.read('trajectory.csv').decode('utf-8-sig')
            return self.import_trajectory({'metadata':metadata,'csv':text})
    def export(self,path):
        p=Path(path).resolve()
        if not p.is_relative_to(self.output.resolve()):raise ValueError('Export path outside task output')
        meta=json.loads((p/'metadata.json').read_text())
        if not meta.get('recording_complete'):raise ValueError('End trajectory recording before export')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            for name in ('trajectory.csv','metadata.json'):z.write(p/name,name)
        return stream.getvalue()

def make_server(service,host='127.0.0.1',port=17865):
    if host not in ('127.0.0.1','localhost'):raise ValueError('First release binds loopback only')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,code,data,kind='application/json'):
            if isinstance(data,dict):data=json.dumps(data,allow_nan=False).encode()
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            try:
                path=urlparse(self.path)
                if path.path=='/api/status':return self.respond(200,service.status())
                if path.path=='/api/export':return self.respond(200,service.export(parse_qs(path.query)['path'][0]),'application/zip')
                names={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
                if path.path not in names:return self.respond(404,{'error':'Not found'})
                file=service.project/'web/static'/names[path.path];data=file.read_bytes()
                if path.path=='/':data=data.replace(b'__CONTROL_TOKEN__',service.token.encode())
                return self.respond(200,data,mimetypes.guess_type(str(file))[0] or 'text/plain')
            except Exception as exc:self.respond(400,{'error':str(exc)})
        def do_POST(self):
            try:
                if not secrets.compare_digest(self.headers.get('X-SV05-Token',''),service.token):return self.respond(403,{'error':'Control token missing'})
                origin=self.headers.get('Origin')
                if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.respond(403,{'error':'Cross-origin control rejected'})
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=64*1024**2:raise ValueError('Invalid request size')
                raw=self.rfile.read(size);path=urlparse(self.path).path
                if path=='/api/import_zip':return self.respond(200,service.import_zip(raw))
                m=json.loads(raw)
                if path=='/api/command':value=service.command(m)
                elif path=='/api/capture':value=service.supervisor.start(m)
                elif path=='/api/task':value=service.supervisor.control(m['task_id'],m['action'])
                elif path=='/api/import':value=service.import_trajectory(m)
                else:return self.respond(404,{'error':'Not found'})
                self.respond(200,value)
            except Exception as exc:self.respond(400,{'error':str(exc)})
    return ThreadingHTTPServer((host,port),Handler)

def serve(service,host='127.0.0.1',port=17865):
    server=make_server(service,host,port)
    try:server.serve_forever()
    finally:service.closed=True;server.server_close()
