"""Discover only active loaded sensors; validate only the selected camera models."""
from .common import ContractError
from .robot.discovery import sensors_from_paths


def selected(entries, ids, kind):
    by_id = {x['id']: x for x in entries}
    if len(by_id) != len(entries):
        raise ContractError('duplicate_sensor', 'Duplicate discovered sensor ID')
    wanted = sorted(by_id) if ids is None else ids
    missing = set(wanted) - set(by_id)
    if missing:
        raise ContractError('unavailable_sensor', kind + ': ' + ','.join(sorted(missing)))
    return [by_id[x] for x in sorted(wanted)]


def attributes(prim):
    result = {}
    for attr in prim.GetAttributes():
        name = attr.GetName()
        if not name.startswith('omni:sensor:'):
            continue
        value = attr.Get()
        if value is None:
            continue
        if not isinstance(value, (str, bool, int, float)):
            try:
                value = list(value)
            except TypeError:
                value = str(value)
        unit={'omni:sensor:tickRate':'Hz','omni:sensor:Core:scanRateBaseHz':'Hz',
              'omni:sensor:Core:instantLidar':'boolean'}.get(name,'unknown; native schema unit not independently verified')
        result[name] = {'value': value, 'usd_type': str(attr.GetTypeName()), 'unit': unit}
    return result


def build(stage, layer, robot_config, job, recording_id):
    from pxr import Usd, UsdGeom, Sdf
    lidar_paths = [str(p.GetPath()) for p in stage.Traverse()
                   if p.IsActive() and p.IsLoaded() and p.GetTypeName() == 'OmniLidar']
    lidars = selected(sensors_from_paths(lidar_paths), job['sensors']['lidar_ids'], 'lidar')
    available = []
    for entry in robot_config['cameras']:
        path = entry['prim_path']
        if entry['id'] == 'back' and not stage.GetPrimAtPath(path):
            path = path.replace('FisheyeBack', 'FisheyeRear')
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsActive() and prim.IsLoaded() and prim.IsA(UsdGeom.Camera):
            available.append({'id': entry['id'], 'prim_path': path})
    cameras = selected(available, job['sensors']['camera_ids'], 'camera')
    if not cameras and not lidars:
        raise ContractError('empty_selection', 'No selected active, loaded sensors')
    overrides = []
    for kind, entries in (('camera', cameras), ('lidar', lidars)):
        for entry in entries:
            prim = stage.GetPrimAtPath(entry['prim_path'])
            entry['sensor_id'] = kind + '/' + entry['id']
            if kind == 'camera':
                if prim.GetAttribute('omni:lensdistortion:model').Get() != 'opencvFisheye':
                    raise ContractError('camera_model', 'Expected actual OpenCV fisheye calibration')
                width, height = map(int, prim.GetAttribute('omni:lensdistortion:opencvFisheye:imageSize').Get())
                if (width, height) != (1920, 1080):
                    raise ContractError('resolution', 'Formal capture requires existing 1920x1080 calibration')
                entry.update(frame_id=entry['id'] + '_optical', topic_prefix='/camera/' + entry['id'],
                    calibration={'model': 'opencv_fisheye', 'width': width, 'height': height,
                    'intrinsics': {n: float(prim.GetAttribute('omni:lensdistortion:opencvFisheye:' + n).Get()) for n in ('fx','fy','cx','cy','k1','k2','k3','k4')},
                    'exposure_attributes': {a.GetName(): {'value': a.Get(), 'usd_type': str(a.GetTypeName()), 'unit': 'native schema'} for a in prim.GetAttributes() if a.GetName().startswith('exposure:') and a.Get() is not None}})
            else:
                if prim.GetAttribute('omni:sensor:Core:instantLidar').Get() is not True:
                    raise ContractError('lidar_model', 'Only Instant LiDAR supported')
                scan = prim.GetAttribute('omni:sensor:Core:scanRateBaseHz').Get()
                if scan != 10:
                    raise ContractError('lidar_frequency', 'Existing scanRateBaseHz must be 10; model will not be changed')
                entry.update(coordinates='sensor_local_cartesian_m',
                    axes_description='Native RTX local Cartesian axes; geometric diagnostics required before quality acceptance')
            attr = prim.GetAttribute('omni:sensor:tickRate')
            before = attr.Get() if attr else None
            if 'OmniSensorAPI' not in prim.GetAppliedSchemas():
                prim.AddAppliedSchema('OmniSensorAPI')
            with Usd.EditContext(stage, layer):
                if not attr:
                    attr = prim.CreateAttribute('omni:sensor:tickRate', Sdf.ValueTypeNames.Float, custom=False)
                attr.Set(10.0)
            overrides.append({'prim_path': entry['prim_path'], 'attribute': attr.GetName(),
                              'before': before, 'after': attr.Get(), 'usd_type': str(attr.GetTypeName()), 'unit': 'Hz'})
            entry['tick_rate_hz'] = float(attr.Get())
            if kind == 'lidar':
                entry['parameters'] = attributes(prim)
    return {'schema_version': 3, 'recording_id': recording_id, 'mount_revision': 0,
            'calibration_revision': 0, 'world_frame': 'world', 'root_frame': 'swing_coordinate',
            'horizontal_frame': 'swing_horizontal_coordinate', 'stage_meters_per_unit': float(UsdGeom.GetStageMetersPerUnit(stage)),
            'stage_up_axis': str(UsdGeom.GetStageUpAxis(stage)), 'cameras': cameras, 'lidars': lidars}, overrides
