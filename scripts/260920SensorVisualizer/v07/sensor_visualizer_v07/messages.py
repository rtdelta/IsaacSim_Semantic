"""ROS imports are confined to the existing system-ROS worker process."""
import json
import numpy as np
from rclpy.serialization import serialize_message
from sensor_msgs.msg import CameraInfo, CompressedImage, PointCloud2, PointField, JointState
from geometry_msgs.msg import PoseStamped, TransformStamped
from tf2_msgs.msg import TFMessage
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from .geometry import rigid_pose, matrix_from_pose, OPTICAL_TO_USD


def header(message, stamp, frame):
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(int(stamp), 10**9)
    message.header.frame_id = frame


def pose_fields(target, matrix):
    position, rotation = rigid_pose(matrix)
    for name, value in zip('xyz', position): setattr(target.position, name, value)
    for name, value in zip('xyzw', rotation): setattr(target.orientation, name, value)


def transform(parent, child, matrix, stamp):
    msg = TransformStamped()
    header(msg, stamp, parent)
    msg.child_frame_id = child
    position, rotation = rigid_pose(matrix)
    for name, value in zip('xyz', position): setattr(msg.transform.translation, name, value)
    for name, value in zip('xyzw', rotation): setattr(msg.transform.rotation, name, value)
    return msg


def topics(registry):
    values = {'/clock': Clock, '/tf': TFMessage, '/joint_states': JointState,
              '/excavator/root_pose': PoseStamped,
              '/sensor_visualizer/run_metadata': String,
              '/sensor_visualizer/camera_metadata': String,
              '/sensor_visualizer/frame_index': String}
    for lidar in registry['lidars']: values[lidar['topic']] = PointCloud2
    for camera in registry['cameras']:
        prefix = '/camera/'+camera['id']
        values[prefix+'/image_raw/compressed'] = CompressedImage
        values[prefix+'/camera_info'] = CameraInfo
        values[prefix+'/pose'] = PoseStamped
    return values


def type_name(cls):
    return cls.__module__.split('.')[0]+'/msg/'+cls.__name__


def build_messages(bundle, registry, clouds, pngs,diagnostics=None):
    stamp = bundle['simulation_time_ns']
    state = bundle['robot']
    root = matrix_from_pose(state['root_position'], state['root_xyzw'])
    horizontal = matrix_from_pose(state['horizontal']['position'], state['horizontal']['xyzw'])
    root_inverse = np.linalg.inv(root)
    messages = []
    def add(topic, message):
        if diagnostics:
            with diagnostics.span('cdr_serialize',topic=topic,group_id=bundle['group_id'],capture_id=bundle.get('capture_id')):
                data=serialize_message(message)
        else: data=serialize_message(message)
        messages.append((topic,data))
    clock = Clock()
    clock.clock.sec, clock.clock.nanosec = divmod(stamp, 10**9)
    add('/clock', clock)
    transforms = [transform('world', 'swing_horizontal_coordinate', horizontal, stamp),
                  transform('swing_horizontal_coordinate', 'swing_coordinate', root@np.linalg.inv(horizontal), stamp)]
    for lidar in registry['lidars']:
        sid = lidar['id']
        points = clouds[sid]
        if points.dtype != np.dtype('<f4') or points.ndim != 2 or points.shape[1] != 3:
            raise ValueError('Expected little-endian XYZ float32 array')
        message = PointCloud2(height=1, width=len(points), is_bigendian=False,
            fields=[PointField(name=n, offset=i*4, datatype=PointField.FLOAT32, count=1) for i,n in enumerate(('x','y','z'))],
            point_step=12, row_step=len(points)*12, is_dense=bool(np.isfinite(points).all()), data=points.tobytes())
        header(message, stamp, lidar['frame_id'])
        add(lidar['topic'], message)
        transforms.append(transform('swing_coordinate', lidar['frame_id'], np.asarray(bundle['lidars'][sid]['to_world'])@root_inverse, stamp))
    for camera in registry['cameras']:
        cid = camera['id']; optical_frame = 'camera_'+cid+'_optical'
        row = bundle['cameras'][cid]
        calibration = camera['calibration']; v = calibration['intrinsics']
        image = CompressedImage(format='rgb8; png compressed rgb8', data=pngs[cid])
        header(image, stamp, optical_frame)
        add(f'/camera/{cid}/image_raw/compressed', image)
        info = CameraInfo(width=calibration['width'], height=calibration['height'], distortion_model='equidistant')
        info.k = [v['fx'],0.,v['cx'],0.,v['fy'],v['cy'],0.,0.,1.]
        info.d = [v[f'k{i}'] for i in range(1,5)]
        info.r = [1.,0.,0.,0.,1.,0.,0.,0.,1.]
        info.p = [v['fx'],0.,v['cx'],0.,0.,v['fy'],v['cy'],0.,0.,0.,1.,0.]
        header(info, stamp, optical_frame)
        add(f'/camera/{cid}/camera_info', info)
        optical = OPTICAL_TO_USD@np.asarray(row['to_world'])
        pose = PoseStamped(); header(pose, stamp, 'world'); pose_fields(pose.pose, optical)
        add(f'/camera/{cid}/pose', pose)
        transforms.append(transform('swing_coordinate', optical_frame, optical@root_inverse, stamp))
    add('/tf', TFMessage(transforms=transforms))
    joints = JointState(name=state['names'], position=state['positions'], velocity=[], effort=[])
    header(joints, stamp, '')
    add('/joint_states', joints)
    pose = PoseStamped(); header(pose, stamp, 'world'); pose_fields(pose.pose, root)
    add('/excavator/root_pose', pose)
    index = {k:v for k,v in bundle.items() if k not in ('robot', 'cameras', 'lidars', 'buffer')}
    index['cameras'] = bundle['cameras']
    index['lidars'] = bundle['lidars']
    add('/sensor_visualizer/frame_index', String(data=json.dumps(index, allow_nan=False)))
    return messages
