"""Offline, lossless ROS 2 MCAP assembly. No Isaac imports or live stage reads."""
from collections import Counter, defaultdict
import hashlib
import heapq
import io
import json
import math
from pathlib import Path
import re
import struct
import time
import uuid

import numpy as np


def camera_id(value):
    value = 'back' if value == 'rear' else value
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('Invalid camera ID')
    return value


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Camera file outside session directory')
    return path


def rigid_pose(rows):
    """USD/Gf row-vector matrix -> ROS position and quaternion XYZW."""
    matrix = np.asarray(rows, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError('Invalid camera matrix')
    if not np.allclose(matrix[:, 3], [0, 0, 0, 1], atol=1e-6):
        raise ValueError('Expected affine Gf matrix')
    r = matrix[:3, :3].T
    if not np.allclose(r.T @ r, np.eye(3), atol=2e-4) or not np.isclose(np.linalg.det(r), 1, atol=2e-4):
        raise ValueError('Camera transform contains scale or reflection')
    # Eigenvector conversion avoids a singularity at 180 degrees (USD -> optical).
    xx, xy, xz = r[0]; yx, yy, yz = r[1]; zx, zy, zz = r[2]
    k = np.array([[xx-yy-zz, xy+yx, xz+zx, zy-yz],
                  [xy+yx, yy-xx-zz, yz+zy, xz-zx],
                  [xz+zx, yz+zy, zz-xx-yy, yx-xy],
                  [zy-yz, xz-zx, yx-xy, xx+yy+zz]]) / 3
    values, vectors = np.linalg.eigh(k)
    q = vectors[:, np.argmax(values)]
    if q[3] < 0: q = -q
    return matrix[3, :3].tolist(), q.tolist()


def calibration_values(calibration):
    if calibration['model'] != 'opencv_fisheye':
        raise ValueError('Unsupported camera distortion model')
    v = calibration['intrinsics']
    if not all(math.isfinite(float(v[n])) for n in ('fx','fy','cx','cy','k1','k2','k3','k4')):
        raise ValueError('Non-finite calibration')
    if min(v['fx'], v['fy'], calibration['width'], calibration['height']) <= 0:
        raise ValueError('Invalid image size or focal length')
    return [v['fx'], 0., v['cx'], 0., v['fy'], v['cy'], 0., 0., 1.], [v[f'k{i}'] for i in range(1, 5)]


def root_matrix(row):
    x,y,z,w = row['root_orientation_xyzw']
    q=np.asarray([x,y,z,w],dtype=float)
    if not np.isfinite(q).all() or not np.isclose(np.dot(q,q),1,atol=1e-4):
        raise ValueError('Invalid root orientation')
    r=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    matrix=np.eye(4);matrix[:3,:3]=r.T;matrix[3,:3]=row['root_position']
    return matrix


def committed_groups(session):
    """Stream only committed groups; never infer a frame from filenames."""
    handles = {}
    previous = -1
    try:
        with (session / 'capture_index.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                group = json.loads(line)
                stamp = int(group['simulation_time_ns'])
                if stamp <= previous: raise ValueError('Camera group times must increase')
                previous = stamp
                frames = {}
                for old_id, item in group['cameras'].items():
                    cid = camera_id(old_id)
                    if cid in frames: raise ValueError('Duplicate camera ID after rear/back mapping')
                    key = item['frame_metadata']
                    if key not in handles: handles[key] = contained(session, key).open(encoding='utf-8')
                    row = json.loads(next(handles[key]))
                    if (int(row['simulation_time_ns']) != stamp or row['frame_index'] != item['frame_index']):
                        raise ValueError('Image/pose/index mismatch')
                    image_path = contained(session, item['image'])
                    if image_path != contained(session, str(Path(key).parent / row['image'])):
                        raise ValueError('Image/index path mismatch')
                    frames[cid] = (image_path, row, old_id)
                yield stamp, frames
    finally:
        for stream in handles.values(): stream.close()


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def assemble(session, output=None):
    import os
    import rosbag2_py
    from rclpy.serialization import serialize_message
    from sensor_msgs.msg import CompressedImage, CameraInfo
    from geometry_msgs.msg import PoseStamped, TransformStamped
    from tf2_msgs.msg import TFMessage
    from std_msgs.msg import String
    from PIL import Image

    session = Path(session).resolve()
    output = Path(output).resolve() if output else session / 'bag_unified'
    if output.exists(): raise FileExistsError('Unified bag already exists: ' + str(output))
    pending = output.with_name(output.name + '.pending_' + uuid.uuid4().hex[:8])
    lock = session / 'unified_export.lock'
    with lock.open('x') as f: f.write(str(os.getpid()))
    started = time.monotonic()
    progress = session / 'unified_export_status.json'
    writer = reader = None
    try:
        meta = json.loads((session / 'session.json').read_text(encoding='utf-8'))
        if meta.get('state') != 'finished': raise ValueError('Finish the original recording before packing')
        summary = json.loads((session / 'capture_summary.json').read_text())
        if summary.get('error'): raise ValueError('Camera capture reported an error; inspect before packing')
        calibrations = {}
        for old_id in summary['camera_ids']:
            cid = camera_id(old_id)
            if cid in calibrations: raise ValueError('Duplicate camera ID')
            calibrations[cid] = json.loads(contained(session, f'cameras/{old_id}/calibration.json').read_text())
            calibrations[cid].update(source_camera_id=old_id,camera_id=cid)
            calibration_values(calibrations[cid])
        if not calibrations: raise ValueError('No cameras in session')
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(session/'bag'), storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
        original_topics = reader.get_all_topics_and_types()
        names = {t.name for t in original_topics}
        extras = {'/sensor_visualizer/camera_metadata': 'std_msgs/msg/String'}
        if '/tf' not in names: extras['/tf'] = 'tf2_msgs/msg/TFMessage'
        for cid in calibrations:
            for suffix, kind in [('image_raw/compressed','sensor_msgs/msg/CompressedImage'),
                                 ('camera_info','sensor_msgs/msg/CameraInfo'), ('pose','geometry_msgs/msg/PoseStamped')]:
                extras[f'/camera/{cid}/{suffix}'] = kind
        if names.intersection(extras): raise ValueError('Source bag already has camera export topics')
        writer = rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(pending), storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
        for topic in original_topics: writer.create_topic(topic)
        for i, (name, kind) in enumerate(extras.items(), start=max([t.id for t in original_topics] or [0])+1):
            writer.create_topic(rosbag2_py.TopicMetadata(id=i,name=name,type=kind,serialization_format='cdr'))
        expected, source_hash = {}, {}
        counts, source_counts, image_counts = Counter(), Counter(), Counter()

        def digest(table, topic, data, stamp):
            h = table.setdefault(topic, hashlib.sha256())
            h.update(struct.pack('<qQ', stamp, len(data))); h.update(data)

        def originals():
            previous = -1
            while reader.has_next():
                topic, data, stamp = reader.read_next()
                if stamp < previous: raise ValueError('Source bag is not ordered by recording timestamp')
                previous = stamp
                source_counts[topic] += 1; digest(source_hash, topic, data, stamp)
                yield stamp, topic, data

        def set_header(msg, stamp, frame):
            msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 10**9)
            msg.header.frame_id = frame

        def set_pose(target, pose):
            position, quaternion = pose
            for axis, value in zip('xyz', position): setattr(target.position, axis, value)
            for axis, value in zip('xyzw', quaternion): setattr(target.orientation, axis, value)

        def cameras():
            group_count = 0
            for stamp, frames in committed_groups(session):
                if set(frames) != set(calibrations): raise ValueError('Incomplete committed camera group')
                if group_count == 0:
                    description = dict(schema_version=1, world_frame=meta['world_frame'], root_frame=meta['root_frame'],
                        optical_axes='X right, Y down, Z forward', quaternion_order='xyzw',
                        time='image acquisition simulation nanoseconds', images='raw distorted fisheye PNG; not rectified',
                        aliases={'rear':'back'}, calibrations=calibrations,
                        distortion_mapping='OpenCV fisheye theta polynomial k1,k2,k3,k4 -> ROS equidistant D',
                        camera_info_projection='R identity, P nominal [K|0]; raw distorted images, no rectification applied',
                        source_session=session.name, camera_capture_summary=summary)
                    msg = String(data=json.dumps(description, ensure_ascii=False, allow_nan=False))
                    yield stamp, '/sensor_visualizer/camera_metadata', serialize_message(msg)
                transforms = []
                for cid, (path, row, old_id) in frames.items():
                    calibration = calibrations[cid]
                    raw = path.read_bytes()
                    with Image.open(io.BytesIO(raw)) as decoded:
                        if decoded.format != 'PNG' or decoded.mode != 'RGB' or decoded.size != (calibration['width'],calibration['height']):
                            raise ValueError('Unexpected image format/dimensions: '+str(path))
                        decoded.load()  # Validate compressed payload, not just its header.
                    frame = f'camera_{cid}_optical'
                    image = CompressedImage(format='rgb8; png compressed rgb8', data=raw)
                    set_header(image, stamp, frame)
                    yield stamp, f'/camera/{cid}/image_raw/compressed', serialize_message(image)
                    info = CameraInfo(width=calibration['width'], height=calibration['height'], distortion_model='equidistant')
                    info.k, info.d = calibration_values(calibration)
                    info.r = [1.,0.,0.,0.,1.,0.,0.,0.,1.]
                    # Conventional monocular nominal P; no rectified image is produced.
                    k = info.k
                    info.p = [k[0],0.,k[2],0.,0.,k[4],k[5],0.,0.,0.,1.,0.]
                    set_header(info, stamp, frame)
                    yield stamp, f'/camera/{cid}/camera_info', serialize_message(info)
                    pose = PoseStamped(); set_header(pose, stamp, meta['world_frame'])
                    set_pose(pose.pose, rigid_pose(row['camera_optical_to_world']))
                    yield stamp, f'/camera/{cid}/pose', serialize_message(pose)
                    optical_to_base = np.diag([1.,-1.,-1.,1.]) @ np.asarray(row['camera_usd_to_base'])
                    if not np.allclose(optical_to_base @ root_matrix(row),row['camera_optical_to_world'],atol=2e-3,rtol=0):
                        raise ValueError('Saved root/camera world and relative transforms disagree')
                    position, quaternion = rigid_pose(optical_to_base)
                    tf = TransformStamped(); set_header(tf, stamp, meta['root_frame']); tf.child_frame_id = frame
                    for axis, value in zip('xyz',position): setattr(tf.transform.translation,axis,value)
                    for axis, value in zip('xyzw',quaternion): setattr(tf.transform.rotation,axis,value)
                    transforms.append(tf); image_counts[cid] += 1
                yield stamp, '/tf', serialize_message(TFMessage(transforms=transforms))
                group_count += 1
                atomic_json(progress,dict(state='packing',groups=group_count,total_groups=summary['complete_groups'],elapsed_s=time.monotonic()-started))
            if group_count != summary['complete_groups']: raise ValueError('Committed group count differs from capture summary')
            if group_count == 0: raise ValueError('No committed camera images')

        for stamp, topic, data in heapq.merge(originals(), cameras(), key=lambda item:item[0]):
            writer.write(topic,data,stamp); digest(expected,topic,data,stamp); counts[topic] += 1
        del writer; writer = None
        del reader; reader = None
        atomic_json(progress,dict(state='verifying',images=dict(image_counts),elapsed_s=time.monotonic()-started))
        check=rosbag2_py.SequentialReader()
        check.open(rosbag2_py.StorageOptions(uri=str(pending),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
        actual={}; actual_counts=Counter()
        while check.has_next():
            topic,data,stamp=check.read_next();digest(actual,topic,data,stamp);actual_counts[topic]+=1
        del check
        if actual_counts != counts or {k:v.hexdigest() for k,v in actual.items()} != {k:v.hexdigest() for k,v in expected.items()}:
            raise ValueError('Unified MCAP read-back verification failed')
        report=dict(schema_version=1,state='complete',source=str(session/'bag'),output=str(output),
            elapsed_s=time.monotonic()-started,groups=summary['complete_groups'],image_counts=dict(image_counts),
            source_counts=dict(source_counts),output_counts=dict(counts),
            original_message_digests={k:v.hexdigest() for k,v in source_hash.items()},
            output_message_digests={k:v.hexdigest() for k,v in actual.items()},
            verification='all output serialized messages and recording timestamps read back; all source messages copied unchanged; all PNGs decoded',
            source_files_retained=True)
        pending.rename(output)
        atomic_json(session/'unified_export_report.json',report)
        atomic_json(progress,report)
        return report
    except Exception as exc:
        atomic_json(progress,dict(state='failed',error=str(exc),partial_output=str(pending),elapsed_s=time.monotonic()-started))
        raise
    finally:
        if writer is not None: del writer
        if reader is not None: del reader
        lock.unlink()
