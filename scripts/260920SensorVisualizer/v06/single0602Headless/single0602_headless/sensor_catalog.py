"""Whole-Stage sensor discovery. No Isaac imports until a Stage is inspected."""
from collections import Counter
from copy import deepcopy
import hashlib
import math
import re


def plain(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    try:
        return [plain(v) for v in value]
    except TypeError:
        return str(value)


def slug(value):
    value = re.sub(r'[^A-Za-z0-9_]', '_', value).strip('_') or 'sensor'
    return 'sensor_' + value if value[0].isdigit() else value


def camera_calibration(attributes, resolution=(1920, 1080)):
    model = str(attributes.get('omni:lensdistortion:model') or '')
    if model == 'opencvFisheye':
        prefix = 'omni:lensdistortion:opencvFisheye:'
        width, height = attributes[prefix + 'imageSize']
        intrinsics = {n: float(attributes[prefix + n]) for n in ('fx', 'fy', 'cx', 'cy', 'k1', 'k2', 'k3', 'k4')}
        result = {'model': 'opencv_fisheye', 'width': int(width), 'height': int(height), 'intrinsics': intrinsics,
                  'resolution_source': 'USD_opencvFisheye_imageSize'}
    elif model == 'opencvPinhole':
        prefix='omni:lensdistortion:opencvPinhole:'
        width,height=attributes[prefix+'imageSize']
        intrinsics={n:float(attributes[prefix+n]) for n in ('fx','fy','cx','cy')}
        coeffs={n:float(attributes.get(prefix+n) or 0.) for n in ('k1','k2','p1','p2','k3','k4','k5','k6')}
        rational=any(coeffs[n] for n in ('k4','k5','k6'))
        result={'model':'opencv_pinhole','width':int(width),'height':int(height),'intrinsics':intrinsics,
                'distortion':[coeffs[n] for n in (('k1','k2','p1','p2','k3','k4','k5','k6') if rational else ('k1','k2','p1','p2','k3'))],
                'distortion_model':'rational_polynomial' if rational else 'plumb_bob','resolution_source':'USD_opencvPinhole_imageSize'}
    elif model or any(any(t in k.lower() for t in ('fisheye', 'ftheta', 'equirectangular'))
                      for k in attributes if attributes[k] is not None):
        raise ValueError('Unsupported or incomplete native lens model: ' + (model or 'specialized projection'))
    else:
        if str(attributes.get('projection', 'perspective')) != 'perspective':
            raise ValueError('Only perspective pinhole cameras are supported')
        width, height = map(int, resolution)
        focal = float(attributes.get('focalLength', 50.))
        ha = float(attributes.get('horizontalAperture', 20.955))
        va = float(attributes.get('verticalAperture', 15.2908))
        if min(focal, ha, va) <= 0:
            raise ValueError('Invalid camera focal length/aperture')
        # USD camera uses horizontal aperture and output aspect for rendering.
        # Author the corresponding vertical aperture in the runtime layer only.
        result = {'model': 'pinhole', 'width': width, 'height': height,
                  'intrinsics': {'fx': focal / ha * width, 'fy': focal / ha * width,
                                 'cx': width / 2. - float(attributes.get('horizontalApertureOffset',0.) or 0.)/ha*width,
                                 'cy': height / 2. + float(attributes.get('verticalApertureOffset',0.) or 0.)/ha*width},
                  'vertical_aperture': ha * height / width, 'distortion': [0., 0., 0., 0., 0.], 'distortion_model':'plumb_bob',
                  'resolution_source': 'job.sensors.camera_resolution', 'focal_length': focal,
                  'horizontal_aperture': ha, 'authored_vertical_aperture': va}
    if result['width'] < 1 or result['height'] < 1 or min(result['intrinsics']['fx'], result['intrinsics']['fy']) <= 0:
        raise ValueError('Invalid camera image size or focal intrinsics')
    if not all(math.isfinite(v) for v in [*result['intrinsics'].values(),*result.get('distortion',[])]):
        raise ValueError('Non-finite camera calibration')
    result.update(exposure={k: plain(v) for k, v in attributes.items() if k.startswith('exposure:')},
                  camera_usd_axes='X right, Y up, -Z forward', camera_optical_axes='X right, Y down, Z forward')
    return result


def candidate_from_record(record, resolution=(1920, 1080)):
    """Type matching and capability checks are independent from USD traversal."""
    attrs = record.get('attributes', {})
    typ = record.get('type_name', '')
    schemas = ' '.join(record.get('schemas', []))
    if typ == 'Camera':
        kind = 'cameras'
    elif typ == 'OmniLidar' or 'OmniLidar' in schemas:
        kind = 'lidars'
    elif 'imu' in typ.lower() or 'imu' in schemas.lower():
        kind = 'imus'
    else:
        return None
    row = {'prim_path': record['path'], 'kind': kind, 'sensor_type': {'cameras': 'camera', 'lidars': 'rtx_lidar', 'imus': 'imu'}[kind],
           'type_name': typ, 'discoverable': True, 'capturable': False, 'selected': False,
           'sampling_domain': 'physics' if kind == 'imus' else 'render', 'issues': [],
           'parameters': {}, 'binding': deepcopy(record.get('binding', {}))}
    try:
        if kind == 'cameras':
            row['calibration'] = camera_calibration(attrs, resolution)
            row['adapter'] = row['calibration']['model']
        elif kind == 'lidars':
            row['adapter'] = 'instant_rtx_lidar'
            row['parameters'] = {k: str(v) for k, v in attrs.items()
                                 if any(t in k for t in ('instantLidar', 'scanType', 'scanRateBaseHz', 'tickRate', 'nearRange', 'farRange'))}
            if not attrs.get('omni:sensor:Core:instantLidar'):
                raise ValueError('Only Instant RTX LiDAR is supported by the frozen capture backend')
        else:
            row.update(adapter='native_physics_imu', formal_capture_supported=False, validation_status='reserved')
            row['parameters'] = {k: plain(v) for k, v in attrs.items() if any(t in k.lower() for t in ('filter', 'period', 'enable', 'gravity'))}
            raise ValueError('IMU interface reserved; official probe and formal synchronization are separate capabilities')
        if row['binding'].get('category') == 'unsupported_dynamic':
            raise ValueError('Sensor depends on an unrecorded moving carrier or animated transform')
        row['capturable'] = True
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        row['issues'].append(str(exc))
    return row


def assign_ids(rows, robot_root, camera_aliases=None, recorded=None):
    """Retain saved IDs; otherwise deterministic names scoped by installation."""
    aliases = camera_aliases or {}
    saved = {v['prim_path']: v for kind in ('cameras', 'lidars', 'imus') for v in (recorded or {}).get(kind, [])}
    bases = {}
    for row in rows:
        path = row['prim_path']; bits = path.rstrip('/').split('/')
        name = bits[-2] if bits[-1].lower() in ('sensor', 'lidar', 'omnilidar') else bits[-1]
        base = aliases.get(path, name) if row['kind'] == 'cameras' else name
        bases[path] = slug(base)
    counts = Counter(bases.values())
    preferred={}
    for base in counts:
        group=[r for r in rows if bases[r['prim_path']]==base]
        named=[r for r in group if r['kind']=='cameras' and r['prim_path'] in aliases]
        onboard=[r for r in group if r['prim_path'].startswith(robot_root.rstrip('/')+'/')]
        choices=named if named else onboard
        if len(choices)==1:preferred[base]=choices[0]['prim_path']
    reserved={row['id'] for row in saved.values()}
    used = {'world', 'swing_coordinate', 'swing_horizontal_coordinate'}
    for row in sorted(rows, key=lambda r: r['prim_path']):
        path = row['prim_path']; sid = bases[path]
        if path in saved:
            sid = saved[path]['id']
        elif (counts[sid] > 1 and preferred.get(sid)!=path) or sid in used or sid in reserved or row['kind'] == 'imus':
            identity = ('robot/' + path[len(robot_root.rstrip('/')) + 1:] if path.startswith(robot_root.rstrip('/') + '/') else 'scene' + path)
            sid += '_' + hashlib.sha256((row['kind'] + '/' + identity).encode()).hexdigest()[:8]
        if sid in used:
            raise ValueError('Sensor ID collision: ' + sid + '; provide a unique saved binding')
        used.add(sid); row['id'] = sid
        row['mount_id'] = 'camera_' + sid if row['kind'] == 'cameras' else sid
        row['frame_id'] = 'camera_' + sid + '_optical' if row['kind'] == 'cameras' else sid
        row['topic'] = ('/camera/' if row['kind'] == 'cameras' else '/imu/' if row['kind'] == 'imus' else '/lidar/') + sid
        if row['kind'] == 'lidars': row['topic'] += '/points'
    # Generated camera frame names can collide with an otherwise distinct LiDAR
    # name. Preserve recorded identities and standard aliases before disambiguating.
    occupied = {'world', 'swing_coordinate', 'swing_horizontal_coordinate'}
    ordered = sorted(rows, key=lambda r: (r['prim_path'] not in saved,
                     r['prim_path'] not in aliases, r['prim_path']))
    for row in ordered:
        path = row['prim_path']; base = row['id']; attempt = 0
        while {row['id'], row['mount_id'], row['frame_id']} & occupied:
            if path in saved:
                raise ValueError('Recorded sensor mount/frame identity collision: ' + path)
            identity = ('robot/' + path[len(robot_root.rstrip('/')) + 1:]
                        if path.startswith(robot_root.rstrip('/') + '/') else 'scene' + path)
            suffix = hashlib.sha256((row['kind'] + '/' + identity + '/' + str(attempt)).encode()).hexdigest()[:8]
            sid = base + '_' + suffix; attempt += 1
            row.update(id=sid, mount_id='camera_' + sid if row['kind'] == 'cameras' else sid,
                       frame_id='camera_' + sid + '_optical' if row['kind'] == 'cameras' else sid,
                       topic=('/camera/' if row['kind'] == 'cameras' else '/imu/' if row['kind'] == 'imus' else '/lidar/') + sid
                             + ('/points' if row['kind'] == 'lidars' else ''))
        occupied.update((row['id'], row['mount_id'], row['frame_id']))
    return rows


def select_candidates(candidates, selection, recorded=None):
    result = {kind: [] for kind in ('cameras', 'lidars', 'imus')}
    known = {v['id']: v for v in candidates}
    if recorded is not None:
        wanted = [v['id'] for kind in result for v in recorded.get(kind, [])]
        missing = set(wanted) - set(known)
        if missing:
            raise ValueError('Recorded sensors missing: ' + ', '.join(sorted(missing)))
    else:
        wanted = []
        for kind in result:
            ids = selection.get(kind[:-1] + '_ids')
            if ids is None:
                wanted += [r['id'] for r in candidates if r['kind'] == kind and r['capturable']]
            else:
                if len(set(ids)) != len(ids): raise ValueError('Duplicate sensor selection')
                if set(ids) - {r['id'] for r in candidates if r['kind'] == kind}:
                    raise ValueError('Unknown ' + kind + ' IDs: ' + str(ids))
                wanted += ids
    for row in candidates:
        row['selected'] = row['id'] in wanted
        if row['selected']:
            if not row['capturable']:
                raise ValueError(row['prim_path'] + ': ' + '; '.join(row['issues']))
            result[row['kind']].append(deepcopy(row))
    return result


def stage_records(stage, robot_root, base_body, controlled_bodies=None):
    from pxr import Usd, UsdGeom, UsdPhysics
    records = []
    for prim in stage.Traverse():
        if not prim.IsActive() or not prim.IsLoaded(): continue
        typ = str(prim.GetTypeName()); schemas = list(map(str, prim.GetAppliedSchemas()))
        if typ not in ('Camera', 'OmniLidar') and 'imu' not in (typ + ' '.join(schemas)).lower() and not any('OmniLidar' in s for s in schemas):
            continue
        if str(prim.GetPath()).startswith('/OmniverseKit_') or prim.GetCustomData().get('single0602_runtime'):
            continue
        attrs = {a.GetName(): plain(a.Get()) for a in prim.GetAttributes()}
        anchor = prim; category = 'world_static'; body = None
        while anchor and not anchor.IsPseudoRoot():
            xf = UsdGeom.Xformable(anchor)
            if any(a.GetNumTimeSamples() for a in anchor.GetAttributes() if a.GetName().startswith('xformOp:')):
                category = 'unsupported_dynamic'; break
            if anchor.HasAPI(UsdPhysics.RigidBodyAPI):
                body = str(anchor.GetPath())
                if body in (controlled_bodies or {base_body}):
                    category = 'robot_body'
                elif not UsdPhysics.RigidBodyAPI(anchor).GetKinematicEnabledAttr().Get():
                    category = 'unsupported_dynamic'
                break
            if str(anchor.GetPath()) == robot_root:
                category = 'robot_root'; body = robot_root; break
            if xf and xf.GetResetXformStack(): break
            anchor = anchor.GetParent()
        records.append({'path': str(prim.GetPath()), 'type_name': typ, 'schemas': schemas, 'attributes': attrs,
            'binding': {'category': category, 'body_path': body,
                        'motion_anchor':base_body if category=='robot_root' else body,
                        'reference': 'world' if category == 'world_static' else body}})
    return records


def discover_sensor_candidates(stage, robot, sensor_config, selection, recorded=None):
    root = robot['robot_prim']
    if recorded is not None:
        recorded=deepcopy(recorded)
        old_root=recorded.get('robot_root',root)
        for kind in ('cameras','lidars','imus'):
            for row in recorded.get(kind,[]):
                if row['prim_path'].startswith(old_root.rstrip('/')+'/'):
                    row['prim_path']=root+row['prim_path'][len(old_root):]
    aliases = {}
    for item in sensor_config.get('cameras', []):
        path = item['prim_path']
        if path.startswith('/World/Excavator/'):
            path = root + path[len('/World/Excavator'):]
        aliases[path] = item['id']
        if item['id'] == 'back': aliases[path.replace('FisheyeBack', 'FisheyeRear')] = item['id']
    bodies={robot['base_body']}|{j[b] for j in robot['joints'].values() for b in ('body0','body1')}
    candidates = [candidate_from_record(r, selection.get('camera_resolution', [1920, 1080]))
                  for r in stage_records(stage, root, robot['base_body'],bodies)]
    candidates = [r for r in candidates if r is not None]
    assign_ids(candidates, root, aliases, recorded)
    registry = select_candidates(candidates, selection, recorded)
    registry.update(schema_version=3, world_frame='world', root_frame='swing_coordinate',
                    horizontal_frame='swing_horizontal_coordinate', id_algorithm='scoped_path_v1',robot_root=root)
    return candidates, registry
