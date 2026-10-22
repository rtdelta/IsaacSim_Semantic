"""Resolve explicit CLI inputs before launching Kit; own an immutable launch job."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from .contracts import load_job, write_json


def resolve_interactive_job(project, *, job_path=None, scene=None, output=None,
                            background_dome=None, asset_profile_id=None, check_files=True):
    project = Path(project).resolve()
    explicit_job = job_path is not None
    path = Path(job_path).resolve() if explicit_job else project / 'config/interactive.json'
    raw = json.loads(path.read_text(encoding='utf-8-sig'))
    changes = {'mode': 'interactive'}
    sources = {'scene': 'job' if explicit_job else 'default',
               'output_directory': 'job' if explicit_job else 'default',
               'background_dome': 'job' if explicit_job and 'background_dome' in raw.get('render', {}) else 'auto'}
    if scene is not None:
        changes['scene'] = scene
        sources['scene'] = 'cli'
        if not explicit_job or 'background_dome' not in raw.get('render', {}):
            changes['render'] = {'background_dome': None}
    if output is not None:
        changes['output_directory'] = str(Path(output).expanduser().resolve())
        sources['output_directory'] = 'cli'
    if background_dome is not None:
        changes.setdefault('render', {})['background_dome'] = background_dome or None
        sources['background_dome'] = 'cli'
    if asset_profile_id is not None:
        changes['asset_profile_id'] = asset_profile_id
    job = load_job(path, changes)
    if 'replay' in job:
        raise ValueError('Interactive launch cannot use a replay job')
    if Path(job['scene']).suffix.lower() not in ('.usd', '.usda', '.usdc'):
        raise ValueError('scene must be a complete .usd/.usda/.usdc Stage')
    if check_files and not Path(job['scene']).is_file():
        raise ValueError('Scene does not exist or is not a readable file: ' + job['scene'])
    if check_files:
        with Path(job['scene']).open('rb') as stream:
            stream.read(1)
    return job, {'configuration_sources': sources, 'source_job': str(path),
                 'explicit_job': explicit_job, 'requested_scene': scene or job['scene']}


def snapshot_launch(job, information):
    job = deepcopy(job)
    launch_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = Path(job['output_directory']) / 'runtime/launches' / launch_id
    directory.mkdir(parents=True, exist_ok=False)
    job['launch'] = {'id': launch_id, 'directory': str(directory.resolve())}
    path = directory / 'job.json'
    write_json(path, job)
    write_json(directory / 'launch.json', dict(information, launch_id=launch_id,
        created_utc=datetime.now(timezone.utc).isoformat(), state='prepared',
        scene=job['scene'], output_directory=job['output_directory'],
        socket=str(Path(job['output_directory']) / 'runtime/engine.sock'),
        asset_profile_id=job.get('asset_profile_id'), job=str(path.resolve())))
    return path.resolve(), job


def write_binding(job, result):
    directory = job.get('launch', {}).get('directory')
    if directory:
        write_json(Path(directory) / 'binding.json', dict(result, launch_id=job['launch']['id']))
