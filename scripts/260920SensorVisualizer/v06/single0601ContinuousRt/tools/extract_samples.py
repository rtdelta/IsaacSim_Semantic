"""Export first/middle/last committed PNG and full XYZ bytes from an actual READY MCAP."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import String


def read(path):return json.loads(path.read_text())
def sha(data):return hashlib.sha256(data).hexdigest()


def extract(directory,destination):
    directory,destination=directory.resolve(),destination.resolve()
    if directory in destination.parents or directory==destination:
        raise RuntimeError('Samples must be outside the immutable dataset')
    manifest=read(directory/'dataset_manifest.json')
    if (directory/'READY').read_bytes()!=(sha((directory/'dataset_manifest.json').read_bytes())+'\n').encode('ascii'):
        raise RuntimeError('Actual READY hash differs')
    if not all(manifest.get(k) is True for k in ('sync_ok','completeness_ok','file_integrity_ok')):
        raise RuntimeError('Samples require independently accepted complete data')
    count=manifest['counts']['readback_verified']
    selected=sorted({0,count//2,count-1})
    destination.mkdir(parents=True,exist_ok=False)
    items=[]
    registry=read(directory/'sensor_registry.json')
    for bag in sorted(directory.glob('epochs/*/segments/*/bag_unified')):
        reader=rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(bag),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
        types={t.name:t.type for t in reader.get_all_topics_and_types()}
        ordinary={}
        while reader.has_next():
            topic,raw,timestamp=reader.read_next()
            if topic in ('/sensor_visualizer/run_metadata','/sensor_visualizer/camera_metadata'):
                continue
            if topic!='/sensor_visualizer/group_commit':
                ordinary[topic]=raw
                continue
            commit=read_string(raw)
            if commit['group_id'] not in selected:
                ordinary.clear()
                continue
            # Commit and CDR byte hashes are rechecked before exporting any sample.
            for desc in commit['messages']:
                data=ordinary[desc['topic']]
                if sha(data)!=desc['cdr_sha256'] or len(data)!=desc['cdr_nbytes']:
                    raise RuntimeError('Sample actual CDR hash differs')
            frame=read_string(ordinary['/sensor_visualizer/frame_index'])
            prefix='group_%06d_'%commit['group_id']
            frame_path=destination/(prefix+'frame_index.json')
            frame_path.write_text(json.dumps(frame,indent=2)+'\n')
            items.append({'path':frame_path.name,'sha256':sha(frame_path.read_bytes()),'group_id':commit['group_id'],'kind':'actual decoded frame_index'})
            for camera in registry['cameras']:
                msg=deserialize_message(ordinary[camera['topic_prefix']+'/image_raw/compressed'],get_message(types[camera['topic_prefix']+'/image_raw/compressed']))
                png=bytes(msg.data)
                e=frame['cameras'][camera['id']]
                with Image.open(io.BytesIO(png)) as image:
                    rgb=np.array(image)
                if rgb.shape!=(1080,1920,3) or sha(png)!=e['encoded_payload_sha256'] or sha(rgb.tobytes())!=e['raw_payload_sha256']:
                    raise RuntimeError('Sample native full-resolution PNG hashes differ')
                path=destination/(prefix+camera['id']+'.png')
                path.write_bytes(png)
                items.append({'path':path.name,'sha256':sha(png),'group_id':commit['group_id'],'kind':'unaltered lossless PNG attachment','resolution':[1920,1080]})
            for lidar in registry['lidars']:
                msg=deserialize_message(ordinary[lidar['topic']],get_message(types[lidar['topic']]))
                xyz=bytes(msg.data)
                if sha(xyz)!=frame['lidars'][lidar['id']]['raw_payload_sha256']:
                    raise RuntimeError('Sample actual XYZ hash differs')
                points=np.frombuffer(xyz,dtype='<f4').reshape(-1,3)
                path=destination/(prefix+lidar['id']+'.xyz.f32le.bin')
                path.write_bytes(xyz)
                items.append({'path':path.name,'sha256':sha(xyz),'group_id':commit['group_id'],'kind':'full native sensor-local XYZ float32 little endian',
                              'points':len(points),'bounds_min_m':points.min(axis=0).tolist() if len(points) else None,
                              'bounds_max_m':points.max(axis=0).tolist() if len(points) else None,
                              'sensor_to_world_usd':frame['state']['sensor_world_matrices_usd'][lidar['sensor_id']]})
            ordinary.clear()
        del reader
    report={'schema_version':1,'source_recording_id':manifest['recording_id'],'rule':'sorted unique group IDs [0, floor(N/2), N-1]',
            'selected_group_ids':selected,'source_manifest_sha256':sha((directory/'dataset_manifest.json').read_bytes()),'files':items,
            'geometry_quality_claim':None,'reason':'Full raw samples and actual matrices are evidence; no automatic geometry/quality pass'}
    (destination/'samples_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def read_string(raw):return json.loads(deserialize_message(raw,String).data)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    report=extract(a.directory,a.output)
    print(json.dumps({'source_recording_id':report['source_recording_id'],'selected_group_ids':report['selected_group_ids'],'exported_files':len(report['files'])}))
