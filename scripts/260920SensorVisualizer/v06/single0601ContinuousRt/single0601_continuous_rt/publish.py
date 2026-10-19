"""Independent closed-file validation and SHA256 discovery publication."""
import json
import os
import time
import shutil
from pathlib import Path
from .common import file_hash,save_json,utc,ContractError
from .validation import validate_recording


def publish(directory):
    directory=Path(directory).resolve()
    if (directory/'READY').exists():
        raise ContractError('immutable_dataset','An existing READY dataset is immutable; use the read-only validator')
    start=time.monotonic()
    session=json.loads((directory/'session.json').read_text())
    shutil.copyfile(directory/'session.json',directory/'readback_session_input.json')
    report,segments=validate_recording(directory)
    complete=report['sync_ok'] and report['file_integrity_ok'] and report['completeness_ok'] and session['outcome']=='completed'
    session['counts']['readback_verified']=report['counts']['groups_verified']
    session['acceptance_results'].update(sync_ok=report['sync_ok'],completeness_ok=report['completeness_ok'])
    session['status']='READY' if complete else ('STOPPED' if session['outcome']=='stopped' else 'FAILED')
    session['ended_utc']=utc()
    if not complete and session['failure'] is None and session['outcome']!='stopped':
        session['failure']={'code':'readback_failed','message':'Independent closed MCAP validation did not authorize complete publication',
                            'evidence_paths':['validation.json']}
        session['outcome']='failed'
    save_json(directory/'session.json',session)
    if (directory/'performance.json').exists():
        performance=json.loads((directory/'performance.json').read_text())
        elapsed=time.monotonic()-start
        performance['wall_times_s']['readback']=elapsed
        performance['wall_times_s']['total']+=elapsed
        performance['throughput']['usable_groups_per_wall_s']=report['counts']['groups_verified']/performance['wall_times_s']['total']
        save_json(directory/'performance.json',performance)
    if not complete:
        destination=directory.parent.parent/'failed'/directory.name
        destination.parent.mkdir(exist_ok=True)
        directory.rename(destination)
        return destination,report
    registry=json.loads((directory/'sensor_registry.json').read_text())
    ranges=[]
    for segment in segments:
        if not segment['frames']:
            continue
        a,b=segment['frames'][0],segment['frames'][-1]
        ranges.append({'epoch_id':a['epoch_id'],'segment_id':a['segment_id'],
            'first_group_id':a['group_id'],'last_group_id':b['group_id'],
            'first_target_index':a['target_index'],'last_target_index':b['target_index'],
            'first_target_step':a['target_step'],'last_target_step':b['target_step'],
            'first_simulation_time_ns':a['simulation_time_ns'],'last_simulation_time_ns':b['simulation_time_ns'],
            'group_count':segment['groups'],'mount_revision':a['mount_revision'],'calibration_revision':a['calibration_revision']})
    def file_entry(path,base):
        return {'path':path.relative_to(base).as_posix(),'format':{'.json':'json','.jsonl':'jsonl','.yaml':'yaml','.mcap':'mcap'}.get(path.suffix,'text'),
                'size_bytes':path.stat().st_size,'sha256':file_hash(path),'produced_by':'P7'}
    core={'schema_version':1,'recording_id':session['recording_id'],'created_utc':utc(),
          'backend':session['backend'],'policy':session['policy'],'completion_class':'complete',
          'source_recording_id':None,'source_outcome':None,
          'selected_sensor_ids':sorted(e['sensor_id'] for k in ('cameras','lidars') for e in registry[k]),
          'counts':{k:session['counts'][k] for k in ('requested','scheduled','validated','written','readback_verified','gap_groups')},
          'sync_ok':True,'completeness_ok':True,'file_integrity_ok':True,'acceptance_results':session['acceptance_results'],'ready':True}
    for r,data in zip(ranges,segments):
        segment=directory/'epochs'/r['epoch_id']/'segments'/r['segment_id']
        shutil.copyfile(directory/'environment.json',segment/'environment.json')
        segment_inputs=[dict(f,path=Path(f['path']).relative_to(segment.relative_to(directory)).as_posix()) for f in report['input_files'] if Path(f['path']).is_relative_to(segment.relative_to(directory))]
        segment_validation=dict(report,scope='segment',epoch_id=r['epoch_id'],segment_id=r['segment_id'],
                                input_files=segment_inputs,
                                counts={'groups_seen':data['groups'],'commits_seen':data['groups'],'groups_verified':data['groups'],
                                        'messages_seen':data['messages'],'incomplete_groups':0,'gap_groups':0},
                                max_abs_source_time_error_ns=str(data['maximum']['source_ns']),max_translation_error_m=data['maximum']['translation_m'],max_rotation_error_rad=data['maximum']['rotation_rad'],
                                checks={k:dict(v,checked_items=data['groups']) for k,v in report['checks'].items()})
        save_json(segment/'validation.json',segment_validation)
        manifest=dict(core,scope='segment',epoch_id=r['epoch_id'],segment_id=r['segment_id'],ranges=[r],validation_path='validation.json',
                      counts={k:r['group_count'] for k in ('requested','scheduled','validated','written','readback_verified')}|{'gap_groups':0},
                      files=[file_entry(p,segment) for p in sorted(segment.rglob('*')) if p.is_file()])
        save_json(segment/'dataset_manifest.json',manifest)
        (segment/'READY').write_text(file_hash(segment/'dataset_manifest.json')+'\n',encoding='ascii')
    # IPC is transport, excluded from discoverable datasets after all worker mappings close.
    for path in (directory/'.ipc').glob('*.mmap'):
        path.unlink()
    if (directory/'.ipc').exists():
        (directory/'.ipc').rmdir()
    files=[file_entry(p,directory) for p in sorted(directory.rglob('*')) if p.is_file()]
    save_json(directory/'dataset_manifest.json',dict(core,scope='recording',epoch_id=None,segment_id=None,
              ranges=ranges,files=files,validation_path='validation.json'))
    (directory/'READY').write_text(file_hash(directory/'dataset_manifest.json')+'\n',encoding='ascii')
    destination=directory.parent.parent/'datasets'/directory.name
    destination.parent.mkdir(exist_ok=True)
    directory.rename(destination)
    return destination,report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('directory')
    result,report=publish(p.parse_args().directory)
    print(json.dumps({'directory':str(result),'sync_ok':report['sync_ok'],'completeness_ok':report['completeness_ok'],
                      'groups_verified':report['counts']['groups_verified']}),flush=True)
