"""Task snapshots own their completed trajectory and do not depend on an owner socket."""
from copy import deepcopy
from pathlib import Path
from .contracts import write_json
from .frame_contract import validate_metadata, file_sha256
from .trajectory import Trajectory


def snapshot_trajectory(source, destination):
    trajectory = Trajectory.load(source)
    validate_metadata(trajectory.metadata, require_complete=True)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    import json
    with (destination / 'states.jsonl').open('x', encoding='utf-8') as stream:
        for state in trajectory.states:
            stream.write(json.dumps(state, ensure_ascii=False, allow_nan=False) + '\n')
    metadata = deepcopy(trajectory.metadata)
    metadata['source_trajectory'] = str(Path(source).resolve())
    metadata['source_file_hashes'] = deepcopy(metadata.get('file_hashes', {}))
    metadata['file_hashes'] = {'states.jsonl': file_sha256(destination / 'states.jsonl')}
    events=Path(source)/'control_events.jsonl'
    if events.is_file():
        (destination/'control_events.jsonl').write_bytes(events.read_bytes())
        metadata['file_hashes']['control_events.jsonl']=file_sha256(destination/'control_events.jsonl')
    write_json(destination / 'metadata.json', metadata)
    return Trajectory.load(destination)


def verify_replay_identity(metadata, scene):
    """Compare recorded asset identity and reference offset to the loaded native state."""
    validate_metadata(metadata, require_complete=True)
    current = scene.motion.frame_metadata()
    for key in ('asset_origin_version', 'swing_zero_mapping', 'root_in_reference_row_matrix'):
        if metadata[key] != current[key]:
            raise ValueError('Replay asset/reference identity differs: ' + key)
    if metadata['joint_definitions'] != scene.motion.config['joints']:
        raise ValueError('Replay joint mapping differs from the recorded asset')
    for layer in metadata['asset_manifest'].get('used_layers', []):
        if file_sha256(layer['path']) != layer['sha256']:
            raise ValueError('Recorded USD dependency changed: ' + layer['path'])
