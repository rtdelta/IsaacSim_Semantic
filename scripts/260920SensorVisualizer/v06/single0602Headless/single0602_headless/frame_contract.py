"""Versioned track-equivalent contract and explicitly pinned asset zero profiles."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

VERSION = 's0602_track_equivalent_v1'
CONTRACT = {'frame_contract_version': VERSION, 'root_frame': 'swing_coordinate',
            'horizontal_frame': 'swing_horizontal_coordinate',
            'keyboard_translation_frame': 'swing_horizontal_coordinate',
            'cab_track_angle_rad': 0., 'cab_track_angle_source': 'assumed_zero'}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def resolve_profile(project, scene):
    profiles = json.loads((Path(project) / 'config/asset_profiles.json').read_text(encoding='utf-8'))['profiles']
    matches = [p for p in profiles if p['scene'] == str(scene)]
    if len(matches) != 1:
        raise ValueError('No declared cab-track zero mapping for this scene; add a verified asset profile')
    profile = deepcopy(matches[0])
    for path, expected in [(scene, profile['scene_sha256']), (profile['asset'], profile['asset_sha256'])]:
        if file_sha256(path) != expected:
            raise ValueError('Asset profile hash mismatch: ' + str(path))
    zero = profile['swing_zero_mapping']
    if not math.isfinite(zero['native_zero_rad']) or zero['engineering_zero_rad'] != 0 or zero['angle_source'] != 'assumed_zero':
        raise ValueError('Invalid declared swing zero mapping')
    return profile


def verify_swing(native, mapping):
    native = float(native)
    error = abs(native - mapping['native_zero_rad'])
    if not math.isfinite(native) or error > mapping['tolerance_rad']:
        raise RuntimeError('cab-track native zero readback failed: error=' + str(error))
    return {'native_angle_rad': native, 'engineering_angle_rad': 0.,
            'angle_source': 'assumed_zero', 'error_rad': error, 'verified': True}


def validate_metadata(metadata, require_complete=False):
    for key, value in CONTRACT.items():
        if metadata.get(key) != value:
            raise ValueError('Incompatible trajectory contract field: ' + key + '; explicit evidence-based migration required')
    for key in ('asset_origin_version', 'swing_zero_mapping', 'root_in_reference_row_matrix', 'joint_definitions', 'asset_manifest'):
        if not metadata.get(key):
            raise ValueError('Missing trajectory identity: ' + key)
    if not metadata.get('swing_zero_readback', {}).get('verified'):
        raise ValueError('Missing startup swing zero verification')
    verify_swing(metadata['swing_zero_readback']['native_angle_rad'], metadata['swing_zero_mapping'])
    if require_complete and metadata.get('recording_complete') is not True:
        raise ValueError('Trajectory must be closed and completely drained')
    return metadata
