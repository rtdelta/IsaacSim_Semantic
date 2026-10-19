"""Run under system ROS Python: source /opt/ros/jazzy/setup.bash first."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v04.contracts import write_json
from sensor_visualizer_v04.geometry import matrix_from_pose, OPTICAL_TO_USD


def validate(session, export_images=False):
    session=Path(session); report=json.loads((session/'writer_report.json').read_text())
    registry=json.loads((session/'sensor_registry.json').read_text())
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in reader.get_all_topics_and_types()}
    counts=Counter(); digests={}; image_count=0; points=0; stamps=[]; seen=set(); current=None; group={}; groups=0
    expected=set(report['counts'])
    def ns(t): return t.sec*10**9+t.nanosec
    def check_group():
        nonlocal groups
        if not group: return
        if seen!=expected: raise ValueError(f'Incomplete group {groups}: {expected-seen}')
        index=json.loads(group['/sensor_visualizer/frame_index'].data)
        if index['group_id']!=groups or index['simulation_time_ns']!=current: raise ValueError('Group order/time mismatch')
        if abs(index['source_clock_after_s']-index['source_clock_before_s'])>1e-9: raise ValueError('Clock changed')
        tf=group['/tf']; matrices={'world':np.eye(4)}
        pending=list(tf.transforms)
        while pending:
            previous=len(pending)
            for transform in list(pending):
                parent=transform.header.frame_id
                if parent not in matrices: continue
                if transform.child_frame_id in matrices: raise ValueError('Duplicate/cyclic TF')
                v=transform.transform.translation; q=transform.transform.rotation
                matrices[transform.child_frame_id]=matrix_from_pose([v.x,v.y,v.z],[q.x,q.y,q.z,q.w])@matrices[parent]
                pending.remove(transform)
            if previous==len(pending): raise ValueError('Disconnected TF')
        for sensor in registry['lidars']:
            np.testing.assert_allclose(matrices[sensor['frame_id']],index['lidars'][sensor['id']]['to_world'],atol=2e-5,rtol=0)
        for camera in registry['cameras']:
            cid=camera['id']; expected_matrix=OPTICAL_TO_USD@np.array(index['cameras'][cid]['to_world'])
            np.testing.assert_allclose(matrices['camera_'+cid+'_optical'],expected_matrix,atol=2e-5,rtol=0)
            p=group[f'/camera/{cid}/pose'].pose
            np.testing.assert_allclose(matrix_from_pose([p.position.x,p.position.y,p.position.z],
                [p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]),expected_matrix,atol=2e-5,rtol=0)
        groups+=1
    while reader.has_next():
        topic,data,stamp=reader.read_next(); message=deserialize_message(data,types[topic])
        if topic not in expected: continue
        if current!=stamp:
            check_group(); current=stamp; stamps.append(stamp); group={}; seen=set()
        if topic in seen: raise ValueError('Duplicate topic in group')
        seen.add(topic); group[topic]=message; counts[topic]+=1
        digests.setdefault(topic,hashlib.sha256()).update(int(stamp).to_bytes(8,'little')+data)
        if hasattr(message,'header') and ns(message.header.stamp)!=stamp: raise ValueError('Header mismatch')
        if topic=='/clock' and ns(message.clock)!=stamp: raise ValueError('Clock mismatch')
        if topic=='/tf' and any(ns(t.header.stamp)!=stamp for t in message.transforms): raise ValueError('TF stamp mismatch')
        if topic.endswith('/compressed'):
            image=Image.open(io.BytesIO(bytes(message.data))); image.load(); image_count+=1
            cid=topic.split('/')[2]; cal=next(c['calibration'] for c in registry['cameras'] if c['id']==cid)
            if image.size!=(cal['width'],cal['height']) or image.mode!='RGB': raise ValueError('Image layout mismatch')
            if export_images and counts[topic]==1:
                directory=session/'validation_images'; directory.mkdir(exist_ok=True); image.save(directory/(cid+'.png'))
        if topic.endswith('/points'):
            if message.point_step!=12 or message.row_step!=message.width*12 or len(message.data)!=message.row_step: raise ValueError('Cloud size mismatch')
            values=np.frombuffer(bytes(message.data),dtype='<f4').reshape(-1,3)
            if not np.isfinite(values[:,:3]).all(): raise ValueError('Nonfinite XYZ')
            points+=len(values)
    check_group()
    if dict(counts)!=report['counts'] or {k:v.hexdigest() for k,v in digests.items()}!=report['digests']: raise ValueError('Serialized payload/hash mismatch')
    if groups!=report['groups']: raise ValueError('Group count mismatch')
    result={'passed':True,'groups':groups,'images':image_count,'points':points,'topics_per_group':len(expected),
            'first_stamp_ns':stamps[0] if stamps else None,'last_stamp_ns':stamps[-1] if stamps else None,
            'mcap_files':len(list((session/'bag_unified').glob('*.mcap'))),'checks':['CDR readback hashes','group completeness','common source time','frozen clock','PNG decoding','PointCloud2 layout','TF composition vs render pose']}
    write_json(session/'validation_report.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('session'); p.add_argument('--export-images',action='store_true'); a=p.parse_args()
    print(json.dumps(validate(a.session,a.export_images),indent=2))
