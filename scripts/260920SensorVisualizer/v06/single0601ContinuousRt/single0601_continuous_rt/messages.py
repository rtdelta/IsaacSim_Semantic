"""ROS message construction and CDR hashes; imported only by the CPU ROS worker."""
import hashlib
import json
import time
import numpy as np
from rclpy.serialization import serialize_message
from sensor_msgs.msg import CameraInfo, CompressedImage, PointCloud2, PointField, JointState
from geometry_msgs.msg import PoseStamped, TransformStamped
from tf2_msgs.msg import TFMessage
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from .geometry import rigid_pose, matrix_from_pose, OPTICAL_TO_USD
from .common import cjson, digest, ContractError


def type_name(cls):
    return cls.__module__.split('.')[0] + '/msg/' + cls.__name__


def topics(registry):
    values = {}
    for c in sorted(registry['cameras'], key=lambda x:x['id']):
        prefix = c['topic_prefix']
        values.update({prefix+'/image_raw/compressed': CompressedImage, prefix+'/camera_info': CameraInfo, prefix+'/pose': PoseStamped})
    for lidar in sorted(registry['lidars'], key=lambda x:x['id']):
        values[lidar['topic']] = PointCloud2
    values.update({'/tf': TFMessage, '/joint_states': JointState, '/excavator/root_pose': PoseStamped,
        '/clock': Clock, '/sensor_visualizer/frame_index': String, '/sensor_visualizer/group_commit': String,
        '/sensor_visualizer/run_metadata': String, '/sensor_visualizer/camera_metadata': String})
    return values


def stamp_fields(stamp, ns):
    sec, nano = divmod(int(ns), 10**9)
    if not -(2**31) <= sec < 2**31:
        raise ContractError('ros_time_overflow', 'ROS Time.sec exceeds int32')
    stamp.sec, stamp.nanosec = sec, nano


def header(msg, ns, frame):
    stamp_fields(msg.header.stamp, ns)
    msg.header.frame_id = frame


def pose_fields(target, matrix):
    p, q = rigid_pose(matrix)
    for n, v in zip('xyz', p):
        setattr(target.position, n, float(v))
    for n, v in zip('xyzw', q):
        setattr(target.orientation, n, float(v))


def tf(parent, child, matrix, ns):
    msg = TransformStamped()
    header(msg, ns, parent)
    msg.child_frame_id = child
    p, q = rigid_pose(matrix)
    for n, v in zip('xyz', p):
        setattr(msg.transform.translation, n, float(v))
    for n, v in zip('xyzw', q):
        setattr(msg.transform.rotation, n, float(v))
    return msg


def encode_group(bundle, registry, arrays, pngs, backend, policy):
    ticket, state = bundle['ticket'], bundle['state']
    ns = int(state['sim_time_ns'])
    frame = {k: ticket[k] for k in ('recording_id','epoch_id','segment_id','group_id','target_index','target_step')}
    frame.update(schema_version=3, simulation_time_ns=str(ns), backend=backend, policy=policy,
                 expected_sensor_ids=ticket['expected_sensor_ids'], state_revision=state['state_revision'],
                 mount_revision=state['mount_revision'], calibration_revision=state['calibration_revision'],
                 state=state, state_sha256=digest(state), cameras={}, lidars={},
                 sync_checks=bundle['sync_checks'], validated_monotonic_ns=bundle['validated_monotonic_ns'])
    for sid, value in bundle['evidence'].items():
        evidence = dict(value)
        for extra in ('producer_array_type','producer_device'):
            evidence.pop(extra, None)
        evidence['raw_payload_sha256'] = hashlib.sha256(memoryview(arrays[sid].reshape(-1)).cast('B')).hexdigest()
        kind, short = sid.split('/', 1)
        if kind == 'camera':
            png = pngs[short]
            evidence.update(camera_model='opencv_fisheye', image_encoding='rgb8', encoded_codec='png',
                            encoded_nbytes=len(png), encoded_payload_sha256=hashlib.sha256(png).hexdigest(),
                            calibration_revision=state['calibration_revision'])
        else:
            evidence.update(fields=['x','y','z'], coordinates='sensor_local_cartesian_m')
        frame['cameras' if kind=='camera' else 'lidars'][short] = evidence
    root = matrix_from_pose(state['root']['position_m'], state['root']['orientation_xyzw'])
    horizontal = matrix_from_pose(state['horizontal']['position_m'], state['horizontal']['orientation_xyzw'])
    root_inverse = np.linalg.inv(root)
    transforms = [tf(registry['world_frame'], registry['horizontal_frame'], horizontal, ns),
                  tf(registry['horizontal_frame'], registry['root_frame'], root@np.linalg.inv(horizontal), ns)]
    messages = []
    def add(topic, message):
        messages.append((topic, type_name(type(message)), serialize_message(message)))
    for camera in sorted(registry['cameras'], key=lambda x:x['id']):
        sid, prefix, optical_frame = camera['id'], camera['topic_prefix'], camera['frame_id']
        image = CompressedImage(format='rgb8; png compressed rgb8', data=pngs[sid])
        header(image, ns, optical_frame)
        add(prefix+'/image_raw/compressed', image)
        cal = camera['calibration']
        v = cal['intrinsics']
        info = CameraInfo(width=cal['width'], height=cal['height'], distortion_model='equidistant')
        info.k = [v['fx'],0.,v['cx'],0.,v['fy'],v['cy'],0.,0.,1.]
        info.d = [v['k%d'%i] for i in range(1,5)]
        info.r = [1.,0.,0.,0.,1.,0.,0.,0.,1.]
        info.p = [v['fx'],0.,v['cx'],0.,0.,v['fy'],v['cy'],0.,0.,0.,1.,0.]
        header(info, ns, optical_frame)
        add(prefix+'/camera_info', info)
        optical = OPTICAL_TO_USD@np.asarray(frame['cameras'][sid]['to_world'])
        pose = PoseStamped()
        header(pose, ns, registry['world_frame'])
        pose_fields(pose.pose, optical)
        add(prefix+'/pose', pose)
        transforms.append(tf(registry['root_frame'], optical_frame, optical@root_inverse, ns))
    for lidar in sorted(registry['lidars'], key=lambda x:x['id']):
        sid = lidar['sensor_id']
        points = arrays[sid]
        if points.dtype != np.dtype('<f4') or not np.isfinite(points).all() or len(points)*12 >= 2**32:
            raise ContractError('point_layout', 'Finite small-endian XYZ float32 within ROS uint32 size required')
        msg = PointCloud2(height=1, width=len(points), fields=[PointField(name=n, offset=i*4, datatype=7, count=1) for i,n in enumerate(('x','y','z'))],
                          is_bigendian=False, point_step=12, row_step=len(points)*12, data=points.tobytes(), is_dense=True)
        header(msg, ns, lidar['frame_id'])
        add(lidar['topic'], msg)
        transforms.append(tf(registry['root_frame'], lidar['frame_id'], np.asarray(frame['lidars'][lidar['id']]['to_world'])@root_inverse, ns))
    add('/tf', TFMessage(transforms=transforms))
    joints = JointState(name=state['joints']['names'], position=state['joints']['position'],
                        velocity=state['joints']['velocity'], effort=state['joints']['effort'])
    header(joints, ns, '')
    add('/joint_states', joints)
    pose = PoseStamped()
    header(pose, ns, registry['world_frame'])
    pose_fields(pose.pose, root)
    add('/excavator/root_pose', pose)
    clock = Clock()
    stamp_fields(clock.clock, ns)
    add('/clock', clock)
    add('/sensor_visualizer/frame_index', String(data=cjson(frame).decode('utf-8')))
    manifest = [{'ordinal': i, 'topic': topic, 'ros_type': typ, 'cdr_nbytes': len(raw), 'cdr_sha256': hashlib.sha256(raw).hexdigest()}
                for i, (topic, typ, raw) in enumerate(messages)]
    commit = {k: frame[k] for k in ('recording_id','epoch_id','segment_id','group_id','target_index','target_step','simulation_time_ns','state_sha256','sync_checks')}
    commit.update(schema_version=1, message_count=len(messages), messages=manifest,
                  group_hash=digest(manifest), encoded_monotonic_ns=str(time.monotonic_ns()))
    messages.append(('/sensor_visualizer/group_commit', 'std_msgs/msg/String', serialize_message(String(data=cjson(commit).decode('utf-8')))))
    return frame, commit, messages
