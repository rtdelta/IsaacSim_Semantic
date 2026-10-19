"""Portable complete-state trajectories. No Isaac or NumPy imports."""
from bisect import bisect_right
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import queue
import threading
import time
import uuid
from .contracts import write_json

SCHEMA = 1

def normalize(q):
    if len(q) != 4 or not all(math.isfinite(float(x)) for x in q):
        raise ValueError('Quaternion requires four finite XYZW components')
    n = math.sqrt(sum(float(x)**2 for x in q))
    if n < 1e-12: raise ValueError('Zero quaternion')
    return [float(x)/n for x in q]

def slerp(a,b,u):
    a,b=normalize(a),normalize(b); dot=sum(x*y for x,y in zip(a,b))
    if dot<0: b=[-x for x in b]; dot=-dot
    if dot>.9995: return normalize([x+u*(y-x) for x,y in zip(a,b)])
    angle=math.acos(max(-1,min(1,dot))); den=math.sin(angle)
    return [math.sin((1-u)*angle)/den*x+math.sin(u*angle)/den*y for x,y in zip(a,b)]

def validate_state(s):
    if s.get('schema_version')!=SCHEMA: raise ValueError('Unsupported state schema')
    for name,n in [('position_world_m',3),('quaternion_xyzw',4)]:
        if len(s[name])!=n or not all(math.isfinite(float(x)) for x in s[name]): raise ValueError('Invalid '+name)
    normalize(s['quaternion_xyzw'])
    if not math.isfinite(float(s['t_sim_s'])) or s['t_sim_s']<0: raise ValueError('Invalid trajectory time')
    if not s['joints_deg'] or not all(math.isfinite(float(x)) for x in s['joints_deg'].values()): raise ValueError('Invalid joints')
    for row in s.get('mounts',[]):
        for name in ('position_m','rotation_deg'):
            if len(row[name])!=3 or not all(math.isfinite(float(x)) for x in row[name]): raise ValueError('Invalid mount')
    json.dumps(s,allow_nan=False)
    return s

class TrajectoryRecorder:
    """One disk owner; bounded queue rejects overload instead of silent row loss."""
    def __init__(self,directory,metadata):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=False)
        self.metadata=deepcopy(metadata); self.metadata.update(schema_version=SCHEMA,quaternion_order='xyzw',
            position_units='metres',joint_units='degrees',time_base='prescribed_control_simulation_seconds',
            recording_complete=False)
        self.q=queue.Queue(4096); self.error=None; self.count=0; self.closed=False; self.origin=None
        write_json(self.directory/'metadata.json',self.metadata)
        self.thread=threading.Thread(target=self._write,name='sv06-trajectory-writer',daemon=True)
        self.thread.start()
    def append(self,state,transition='continuous'):
        if self.closed or self.error: raise RuntimeError(self.error or 'Trajectory closed')
        row=deepcopy(validate_state(state))
        row['quaternion_xyzw']=normalize(row['quaternion_xyzw'])
        if self.origin is None: self.origin=float(row['t_sim_s'])
        row['control_time_original_s']=row['t_sim_s'];row['t_sim_s']-=self.origin
        row['seq']=self.count;row['transition_kind']=transition;row['recorded_monotonic_ns']=time.monotonic_ns()
        try: self.q.put_nowait(row)
        except queue.Full:
            self.error='trajectory_backpressure: recording stopped without silently dropping rows'; raise RuntimeError(self.error)
        self.count+=1
    def _write(self):
        try:
            names=None; writer=None
            with (self.directory/'states.jsonl').open('x',encoding='utf-8') as jf, (self.directory/'trajectory.csv').open('x',newline='',encoding='utf-8') as cf:
                last_flush=time.monotonic()
                while True:
                    row=self.q.get()
                    if row is None: break
                    self.metadata['last_time_s']=row['t_sim_s']
                    if names is None:
                        names=sorted(row['joints_deg']); columns=['seq','t_sim_s','state_revision','mount_revision','transition_kind',
                            'base_x_m','base_y_m','base_z_m','base_qx','base_qy','base_qz','base_qw']+['joint_'+n+'_deg' for n in names]
                        writer=csv.writer(cf); writer.writerow(columns); self.metadata['joint_names']=names
                    revisions=self.metadata.setdefault('mount_revisions',{})
                    revision=str(row['mount_revision'])
                    if revision not in revisions or 'control_origin_s' not in self.metadata:
                        revisions[revision]=row['mounts'];self.metadata['control_origin_s']=self.origin
                        write_json(self.directory/'metadata.json',self.metadata)
                    compact={k:v for k,v in row.items() if k not in ('mounts','base_control')}
                    jf.write(json.dumps(compact,ensure_ascii=False,allow_nan=False)+'\n')
                    writer.writerow([row['seq'],row['t_sim_s'],row['state_revision'],row['mount_revision'],row['transition_kind'],
                        *row['position_world_m'],*row['quaternion_xyzw'],*[row['joints_deg'][n] for n in names]])
                    if time.monotonic()-last_flush>.25: jf.flush(); cf.flush(); last_flush=time.monotonic()
        except Exception as exc: self.error=str(exc)
    def close(self):
        if self.closed: return self.directory
        self.closed=True
        while self.thread.is_alive():
            try: self.q.put(None,timeout=.1); break
            except queue.Full: continue
        self.thread.join(timeout=15)
        if self.thread.is_alive(): self.error='Trajectory writer failed to drain'
        self.metadata.update(rows=self.count,recording_complete=self.error is None,error=self.error,control_origin_s=self.origin)
        write_json(self.directory/'metadata.json',self.metadata)
        if self.error: raise RuntimeError(self.error)
        return self.directory

class Trajectory:
    def __init__(self,states,metadata=None):
        if not states: raise ValueError('Empty trajectory')
        if len(states)>1_000_000: raise ValueError('Trajectory row limit exceeded')
        self.states=[deepcopy(validate_state(x)) for x in states]; self.metadata=metadata or {}
        for row in self.states:row['quaternion_xyzw']=normalize(row['quaternion_xyzw'])
        names=set(states[0]['joints_deg']); self.times=[float(x['t_sim_s']) for x in states]
        if any(b<a for a,b in zip(self.times,self.times[1:])): raise ValueError('Trajectory times must be nondecreasing')
        if any(set(x['joints_deg'])!=names for x in states): raise ValueError('Joint mapping changes within trajectory')
        self.duration=self.times[-1]-self.times[0]
    @classmethod
    def load(cls,path):
        p=Path(path); metadata=json.loads((p/'metadata.json').read_text(encoding='utf-8'))
        if (p/'states.jsonl').is_file():
            states=[json.loads(x) for x in (p/'states.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
            revisions=metadata.get('mount_revisions',{})
            for s in states:
                revision=str(s['mount_revision'])
                if revisions and revision not in revisions:raise ValueError('Missing mount revision snapshot')
                s['mounts']=deepcopy(revisions.get(revision,metadata.get('initial_mounts',[])))
        else:
            with (p/'trajectory.csv').open(encoding='utf-8-sig',newline='') as f: states=cls.from_csv(f.read(),metadata).states
        return cls(states,metadata)
    @classmethod
    def from_csv(cls,text,metadata):
        names=metadata['joint_names']; states=[]; mounts=metadata.get('initial_mounts',[])
        import io
        for row in csv.DictReader(io.StringIO(text)):
            revision=int(row['mount_revision']); revisions=metadata.get('mount_revisions',{})
            if str(revision) in revisions: mounts=revisions[str(revision)]
            elif revisions or (states and revision!=states[-1]['mount_revision']): raise ValueError('Missing mount revision snapshot')
            states.append({'schema_version':SCHEMA,'snapshot_id':uuid.uuid4().hex,'t_sim_s':float(row['t_sim_s']),
                'state_revision':int(row['state_revision']),'mount_revision':revision,'mounts':deepcopy(mounts),
                'position_world_m':[float(row['base_'+k+'_m']) for k in 'xyz'],
                'quaternion_xyzw':[float(row['base_q'+k]) for k in 'xyzw'],
                'joints_deg':{n:float(row['joint_'+n+'_deg']) for n in names},'transition_kind':row.get('transition_kind','continuous')})
        return cls(states,metadata)
    def sample(self,elapsed):
        t=float(elapsed)+self.times[0]; i=max(0,bisect_right(self.times,t)-1)
        a=self.states[i]; out=deepcopy(a); out['t_sim_s']=float(elapsed)
        if i<len(self.states)-1:
            b=self.states[i+1]; span=b['t_sim_s']-a['t_sim_s']
            if span>0 and b.get('transition_kind')!='direct' and a['mount_revision']==b['mount_revision']:
                u=max(0,min(1,(t-a['t_sim_s'])/span))
                out['position_world_m']=[x+u*(y-x) for x,y in zip(a['position_world_m'],b['position_world_m'])]
                out['quaternion_xyzw']=slerp(a['quaternion_xyzw'],b['quaternion_xyzw'],u)
                out['joints_deg']={n:x+u*(b['joints_deg'][n]-x) for n,x in a['joints_deg'].items()}
        out['snapshot_id']=uuid.uuid4().hex
        return validate_state(out)
