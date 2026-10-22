"""Recompute geometry on all fixed-rule local samples; keep original reports immutable."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from single0601_continuous_rt.geometry_diagnostics import measure
from single0601_continuous_rt.common import file_hash,save_json


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('samples',type=Path)
    p.add_argument('--registry',type=Path,required=True)
    p.add_argument('--geometry',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    registry=json.loads(a.registry.read_text())
    spec=json.loads(a.geometry.read_text())
    rows=[]
    for path in sorted(a.samples.glob('*frame_index.json')):
        frame=json.loads(path.read_text())
        prefix='group_%06d_'%frame['group_id']
        decoded={}
        for c in registry['cameras']:
            decoded[c['topic_prefix']+'/image_raw/compressed']=SimpleNamespace(data=(a.samples/(prefix+c['id']+'.png')).read_bytes())
        for lidar in registry['lidars']:
            decoded[lidar['topic']]=SimpleNamespace(data=(a.samples/(prefix+lidar['id']+'.xyz.f32le.bin')).read_bytes())
        rows.append(measure(frame,decoded,registry,spec))
    save_json(a.output,{'schema_version':1,'scope':'all first/middle/last rule samples; distinct external measurement, no original report changes',
        'extractor_sha256':file_hash(Path(__file__).resolve().parents[1]/'single0601_continuous_rt/geometry_diagnostics.py'),
        'input_files':[{'path':str(f),'sha256':file_hash(f)} for f in sorted(a.samples.iterdir()) if f.is_file()],
        'full_quality_acceptance':None,'rows':rows})
    print(json.dumps(rows))
