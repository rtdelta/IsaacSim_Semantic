"""Configuration and independent column-vector kinematics; NumPy only."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_config(path=None):
    return json.loads(Path(path or ROOT / 'config/assembly.json').read_text(encoding='utf-8'))


def rotation(axis, angle_deg):
    a = math.radians(angle_deg); c, s = math.cos(a), math.sin(a)
    return np.array({'X': [[1,0,0],[0,c,-s],[0,s,c]],
                     'Y': [[c,0,s],[0,1,0],[-s,0,c]],
                     'Z': [[c,-s,0],[s,c,0],[0,0,1]]}[axis], dtype=float)


def transform(xyz=(0,0,0), r=None, scale=1):
    m=np.eye(4); m[:3,3]=xyz
    m[:3,:3]=(np.eye(3) if r is None else r)*scale
    return m


def raw_to_base(config):
    c=config['reconstruction_to_base']; roll,pitch,yaw=c['rpy_deg']
    return transform(c['translation_m'], rotation('Z',yaw) @ rotation('Y',pitch) @ rotation('X',roll), c['uniform_scale'])


def forward(config, degrees=None):
    degrees=degrees or {}; frames={'base_link':np.eye(4), 'track_link':np.eye(4)}
    for j in config['joints']:
        local=transform(j['xyz_m'], rotation(j['axis'],degrees.get(j['name'],0)))
        frames[j['child_frame']]=frames[j['parent_frame']] @ local
    return frames


def points(matrix, xyz):
    return np.asarray(xyz) @ matrix[:3,:3].T + matrix[:3,3]


def write_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
