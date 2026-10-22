"""Explicit scene selection, portable interfaces and rigid trajectory placement."""
from copy import deepcopy
import json
import math
from pathlib import Path

INTERFACE_VERSION = 2


def placement_options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {'translation_m', 'yaw_deg'}:
        raise ValueError('placement requires translation_m and yaw_deg')
    translation = value.get('translation_m', [0., 0., 0.])
    yaw = value.get('yaw_deg', 0.)
    if not isinstance(translation, (list, tuple)) or len(translation) != 3:
        raise ValueError('placement.translation_m requires three numbers')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
           for x in [*translation, yaw]):
        raise ValueError('placement values must be finite numbers')
    return {'translation_m': list(map(float, translation)), 'yaw_deg': float(yaw)}


def scene_selection(payload, metadata, check_files=False):
    policy = payload.get('scene_policy', 'original')
    if policy not in ('original', 'environment'):
        raise ValueError('scene_policy must be original or environment')
    sensor_policy=payload.get('sensor_policy','recorded')
    if sensor_policy not in ('recorded','target_scene') or (sensor_policy=='target_scene' and policy!='environment'):
        raise ValueError('Target scene sensor policy requires environment capture')
    source = metadata.get('scene')
    target = payload.get('target_scene') or source
    placement = payload.get('placement')
    if placement is None:
        try:
            placement = {'translation_m': [float(payload.get('placement_'+k+'_m', 0)) for k in 'xyz'],
                         'yaw_deg': float(payload.get('placement_yaw_deg', 0))}
        except (ValueError, TypeError):
            raise ValueError('Invalid trajectory placement') from None
    placement = placement_options(placement)
    if policy == 'original':
        if target != source or any(placement['translation_m']) or placement['yaw_deg']:
            raise ValueError('Choose environment policy to change the scene or trajectory placement')
    elif not payload.get('target_scene'):
        raise ValueError('Select target_scene for environment capture; the edited source path is also allowed')
    if not isinstance(target, str) or not target.startswith('/'):
        raise ValueError('target_scene must be an absolute Linux USD path')
    if check_files and not Path(target).is_file():
        raise ValueError('Target scene does not exist: ' + target)
    dome = payload.get('background_dome')
    if dome == '':
        dome = None
    if dome is not None and (not isinstance(dome, str) or not dome.startswith('/')):
        raise ValueError('background_dome must be an absolute USD prim path')
    render = deepcopy(metadata.get('render', {}))
    if policy == 'environment':
        render['background_dome'] = dome
    elif dome is not None and dome != render.get('background_dome'):
        raise ValueError('Choose environment policy to change the DomeLight')
    return {'scene_policy': policy, 'sensor_policy':sensor_policy,'source_scene': source, 'target_scene': target,
            'placement': placement, 'render': render}


def place_state(state, placement=None):
    """Active yaw rotation about world origin followed by world translation."""
    placement = placement_options(placement)
    out = deepcopy(state)
    angle = math.radians(placement['yaw_deg'])
    c, s = math.cos(angle), math.sin(angle)
    x, y, z = state['position_world_m']
    dx, dy, dz = placement['translation_m']
    out['position_world_m'] = [c*x-s*y+dx, s*x+c*y+dy, z+dz]
    x, y, z, w = state['quaternion_xyzw']
    sn, cs = math.sin(angle/2), math.cos(angle/2)
    out['quaternion_xyzw'] = [cs*x-sn*y, cs*y+sn*x, cs*z+sn*w, cs*w-sn*z]
    return out


def compare_interface(expected, actual, path='interface', tolerance=1e-6):
    """Return the first meaningful difference; do not compare absolute asset paths."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            raise ValueError('Incompatible '+path+': fields differ')
        for key in expected:
            compare_interface(expected[key], actual[key], path+'.'+str(key), tolerance)
    elif isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(expected) != len(actual):
            raise ValueError('Incompatible '+path+': length differs')
        for i, (a, b) in enumerate(zip(expected, actual)):
            compare_interface(a, b, path+'['+str(i)+']', tolerance)
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        if not math.isfinite(float(expected)) or isinstance(actual, bool) or not isinstance(actual, (float, int)) or not math.isfinite(float(actual)) or abs(expected-actual) > tolerance:
            raise ValueError('Incompatible '+path+': '+str(expected)+' != '+str(actual))
    elif expected != actual:
        raise ValueError('Incompatible '+path+': '+str(expected)+' != '+str(actual))


def relative_path(path, robot):
    path, robot = str(path), str(robot)
    if path == robot:
        return '.'
    if path.startswith(robot+'/'):
        return path[len(robot)+1:]
    raise ValueError('Binding is outside the excavator: '+path)


def quaternion(q):
    values = [float(q.GetReal()), *map(float, q.GetImaginary())]
    norm = math.sqrt(sum(x*x for x in values))
    if norm < 1e-12 or not math.isfinite(norm):
        raise ValueError('Invalid joint quaternion')
    values = [x/norm for x in values]
    # q and -q represent the same rotation, including 180-degree rotations.
    sign = next((1 if x > 0 else -1 for x in values if abs(x) > 1e-12), 1)
    return [sign*x for x in values]


def motion_interface(stage, binding):
    from pxr import Usd, UsdGeom, UsdPhysics
    robot = binding['robot_prim']
    joints = {}
    for role, item in binding['joints'].items():
        prim = stage.GetPrimAtPath(item['path'])
        joint = UsdPhysics.RevoluteJoint(prim)
        joints[role] = {'name': prim.GetName(), 'path': relative_path(prim.GetPath(), robot),
            'body0': relative_path(joint.GetBody0Rel().GetTargets()[0], robot),
            'body1': relative_path(joint.GetBody1Rel().GetTargets()[0], robot),
            'axis': str(joint.GetAxisAttr().Get()),
            'local_pos0': list(map(float, joint.GetLocalPos0Attr().Get())),
            'local_pos1': list(map(float, joint.GetLocalPos1Attr().Get())),
            'local_rot0_wxyz': quaternion(joint.GetLocalRot0Attr().Get()),
            'local_rot1_wxyz': quaternion(joint.GetLocalRot1Attr().Get()),
            'angle_zero': prim.GetCustomData().get('angleZero')}
    # Reject hidden extra articulation DOFs rather than recognizing four names only.
    expected = {item['path'] for item in binding['joints'].values()}
    for prim in Usd.PrimRange(stage.GetPrimAtPath(robot)):
        if prim.IsA(UsdPhysics.Joint) and UsdPhysics.Joint(prim).GetJointEnabledAttr().Get():
            if str(prim.GetPath()) not in expected and not prim.IsA(UsdPhysics.FixedJoint):
                raise ValueError('Unsupported additional excavator joint: '+str(prim.GetPath()))
    scales = {}
    cache = UsdGeom.XformCache()
    for path in sorted({item['body0'] for item in binding['joints'].values()} | {item['body1'] for item in binding['joints'].values()}):
        matrix = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(path))
        vectors = [[float(matrix[i][j]) for j in range(3)] for i in range(3)]
        lengths = [math.sqrt(sum(v*v for v in row)) for row in vectors]
        if not math.isfinite(matrix.GetDeterminant()) or matrix.GetDeterminant() <= 0 or any(not math.isfinite(x) or x < 1e-9 for x in lengths):
            raise ValueError('Mirrored or degenerate excavator body: '+path)
        if any(abs(sum(vectors[i][k]*vectors[j][k] for k in range(3))/(lengths[i]*lengths[j])) > 1e-6 for i in range(3) for j in range(i)):
            raise ValueError('Sheared excavator body: '+path)
        scales[relative_path(path, robot)] = lengths
    return {'joints': joints, 'body_scales': scales}


def describe_interface(scene):
    from pxr import UsdGeom, UsdPhysics
    robot = scene.config['robot_motion']['robot_prim']
    sensors = {}
    for sensor in scene.registry['lidars']+scene.registry['cameras']:
        sid = 'camera_'+sensor['id'] if 'calibration' in sensor else sensor['id']
        entry = scene.poses.entries[sid]
        parent = scene.stage.GetPrimAtPath(entry['parent_path'])
        binding=sensor.get('binding',{})
        category=binding.get('category','robot_body')
        body_path=entry.get('virtual_anchor') or binding.get('body_path')
        anchor = scene.stage.GetPrimAtPath(body_path) if body_path else parent
        if not binding:
            while anchor and not anchor.IsPseudoRoot() and not anchor.HasAPI(UsdPhysics.RigidBodyAPI):anchor=anchor.GetParent()
        if category=='unsupported_dynamic':raise ValueError('Unrecorded sensor carrier: '+sid)
        cache = UsdGeom.XformCache()
        if entry.get('reference')=='world':
            parent_matrix=cache.GetLocalToWorldTransform(scene.stage.GetPseudoRoot())
        elif 'virtual_anchor' in entry:
            parent=anchor
            parent_matrix=cache.GetLocalToWorldTransform(anchor)*cache.GetLocalToWorldTransform(anchor).GetInverse()
        else:
            parent_matrix = cache.GetLocalToWorldTransform(parent)
            if category!='world_static':parent_matrix=parent_matrix*cache.GetLocalToWorldTransform(anchor).GetInverse()
        path_value=lambda p:str(p) if category=='world_static' else relative_path(p,robot)
        mount = scene.stage.GetPrimAtPath(entry['mount_path'])
        local = UsdGeom.Xformable(mount).GetLocalTransformation()
        scale = [math.sqrt(sum(float(local[i][j])**2 for j in range(3))) for i in range(3)]
        sensors[sid] = {'prim': path_value(sensor['prim_path']),
            'mount': path_value(entry['mount_path']), 'parent': path_value(parent.GetPath()),
            'body': 'world' if category=='world_static' else relative_path(anchor.GetPath(), robot),
            'category':category,
            'parent_in_body': [[float(parent_matrix[i][j]) for j in range(4)] for i in range(4)],
            'mount_scale': scale, 'type': scene.stage.GetPrimAtPath(sensor['prim_path']).GetTypeName(),
            'configuration': deepcopy(sensor.get('calibration', sensor.get('parameters', {})))}
    zero = scene.asset_profile['swing_zero_mapping']
    return {'schema_version': INTERFACE_VERSION, 'up_axis': str(UsdGeom.GetStageUpAxis(scene.stage)),
            'metres_per_unit': UsdGeom.GetStageMetersPerUnit(scene.stage),
            'motion': deepcopy(scene.motion_interface), 'sensors': sensors,
            'zero': {k: zero[k] for k in ('joint_name', 'native_zero_rad', 'engineering_zero_rad', 'angle_source')},
            'root_in_reference': scene.motion.frame_metadata()['root_in_reference_row_matrix']}


def recorded_interface(metadata, project):
    interface = metadata.get('scene_interface')
    if interface:
        if not isinstance(interface,dict) or interface.get('schema_version') not in (1,INTERFACE_VERSION):
            raise ValueError('Unsupported scene_interface version')
        return interface
    # Curated baselines are evidence for older files, never inferred from the target.
    path = Path(project)/'config/legacy_scene_interfaces.json'
    baselines = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    manifest = metadata.get('asset_manifest', {})
    item = baselines.get(manifest.get('root_sha256'))
    if item and manifest.get('asset_profile', {}).get('asset_sha256') == item.get('asset_sha256'):
        identities = lambda rows: sorted((row['path'], row['sha256']) for row in rows)
        if identities(manifest.get('used_layers', [])) != identities(item.get('used_layers', [])) or not item.get('used_layers'):
            raise ValueError('Legacy trajectory USD identity is outside the verified interface baseline')
        compare_interface(item['interface']['root_in_reference'], metadata['root_in_reference_row_matrix'], 'legacy.root_in_reference')
        compare_interface(item['interface']['zero'], {k:metadata.get('swing_zero_mapping',{}).get(k) for k in item['interface']['zero']}, 'legacy.zero')
        return item['interface']
    raise ValueError('Trajectory has no verified scene interface; record a new trajectory or provide an evidence-based legacy baseline')


def comparable_interfaces(source,target,sensor_policy='recorded'):
    """Normalize only evidenced version additions; retain legacy validation."""
    source,target=deepcopy(source),deepcopy(target)
    if sensor_policy=='target_scene':
        source.pop('sensors',None);target.pop('sensors',None)
        source.pop('schema_version',None);target.pop('schema_version',None)
    elif source.get('schema_version')==1 and target.get('schema_version')==2:
        target['schema_version']=1
        for row in target['sensors'].values():
            if row.get('category')!='robot_body':raise ValueError('Legacy recorded sensor must retain its robot body reference')
            row.pop('category',None)
            if row.get('configuration',{}).get('model')=='opencv_fisheye':
                row['configuration'].pop('resolution_source',None)
    return source,target


def replay_registry(metadata,project):
    if metadata.get('sensor_registry') is not None:return deepcopy(metadata['sensor_registry'])
    root=metadata.get('robot_binding',{}).get('robot_prim','/World/Excavator')
    registry={'cameras':[],'lidars':[],'imus':[],'robot_root':root}
    mounts=metadata.get('initial_mounts')
    if isinstance(mounts,list) and all(isinstance(row.get('prim_path'),str) for row in mounts):
        for row in mounts:
            camera=row['id'].startswith('camera_')
            registry['cameras' if camera else 'lidars'].append({'id':row['id'][7:] if camera else row['id'],'prim_path':row['prim_path']})
        return registry
    interface=recorded_interface(metadata,project)
    for sid,row in interface['sensors'].items():
        camera=sid.startswith('camera_')
        kind='cameras' if camera else 'lidars'
        path=row['prim']
        registry[kind].append({'id':sid[len('camera_'):] if camera else sid,
                              'prim_path':path if path.startswith('/') else root+'/'+path})
    return registry
