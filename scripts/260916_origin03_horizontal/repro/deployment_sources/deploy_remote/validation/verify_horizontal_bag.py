"""Verify serialized MCAP TF edges, timestamps, tilt split and world root pose."""
import json
from pathlib import Path
import sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lidar_visualizer.reference_frames import quaternion_matrix


def stamp(s):
    return s.sec*1_000_000_000+s.nanosec


def transform(t):
    p,q=t.translation,t.rotation
    m=np.eye(4);m[:3,:3]=quaternion_matrix([q.x,q.y,q.z,q.w]);m[:3,3]=[p.x,p.y,p.z]
    return m


def verify(session):
    manifest=json.loads((session/'session.json').read_text())
    names={s['frame_id'] for s in manifest['sensors']}
    W,H,S='world','swing_horizontal_coordinate','swing_coordinate'
    expected={(W,H),(H,S)}|{(S,s) for s in names}
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={x.name:get_message(x.type) for x in reader.get_all_topics_and_types()}
    frames,poses,counts,parents,joints={}, {}, {}, {}, {}
    while reader.has_next():
        topic,data,_=reader.read_next()
        counts[topic]=counts.get(topic,0)+1
        msg=deserialize_message(data,types[topic])
        if topic=='/tf':
            for tf in msg.transforms:
                edge=(tf.header.frame_id,tf.child_frame_id)
                assert edge in expected,edge
                parents.setdefault(edge[1],set()).add(edge[0])
                frames.setdefault(stamp(tf.header.stamp),{})[edge]=transform(tf.transform)
        elif topic=='/excavator/root_pose':
            poses[stamp(msg.header.stamp)]=msg.pose
        elif topic=='/joint_states':
            assert list(msg.name)==['swing','boom','arm','bucket']
            assert len(msg.position)==4 and not msg.velocity and not msg.effort
            joints[stamp(msg.header.stamp)]=list(msg.position)
    assert len(parents)==15 and all(len(v)==1 for v in parents.values()),parents
    complete={t:v for t,v in frames.items() if set(v)==expected}
    assert len(complete)>10,(len(complete),counts)
    pose_error=0.;compared=0;tilted=0;max_mount_change=0.;baseline=None
    for t,edges in sorted(complete.items()):
        wh,hs=edges[(W,H)],edges[(H,S)]
        np.testing.assert_allclose(wh[:3,2],[0,0,1],atol=2e-6)
        np.testing.assert_allclose(hs[:3,3],0,atol=2e-6)
        ws=wh@hs
        pkey=next((k for k in (t,t+1,t-1) if k in poses),None)
        if pkey is not None:
            p=poses[pkey]
            pmat=np.eye(4);q=p.orientation
            pmat[:3,:3]=quaternion_matrix([q.x,q.y,q.z,q.w])
            pmat[:3,3]=[p.position.x,p.position.y,p.position.z]
            error=float(np.max(np.abs(ws-pmat)));pose_error=max(error,pose_error)
            assert error<2e-5,(t,error)
            assert pkey in joints
            compared+=1
        if np.max(np.abs(hs[:3,:3]-np.eye(3)))>.05: tilted+=1
        mounts={s:edges[(S,s)] for s in names}
        if baseline is None: baseline=mounts
        max_mount_change=max(max_mount_change,max(float(np.max(np.abs(mounts[s]-baseline[s]))) for s in names))
    assert compared>10 and tilted>10,(compared,tilted)
    assert max_mount_change<2e-4,max_mount_change
    assert manifest['scene']['frame_convention_version']=='swing_horizontal_v1'
    return {'passed':True,'session':str(session),'counts':counts,'edges':sorted([list(e) for e in expected]),
            'complete_tf_timestamps':len(complete),'root_pose_comparisons':compared,'tilted_samples':tilted,
            'max_world_root_matrix_error':pose_error,'max_sensor_mount_matrix_change':max_mount_change,
            'timestamp_matching':'exact or +/-1 ns for native TF double-to-nanoseconds conversion',
            'scope':'TF and state only; no pointcloud rendering in this QA run'}


if __name__=='__main__':
    out=ROOT/'validation/results/origin03_horizontal'
    result=json.loads((out/'kit_validation.json').read_text())
    assert result['passed'],result
    report=verify(Path(result['bag_session']))
    (out/'bag_validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
