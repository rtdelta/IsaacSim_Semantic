"""Audit existing recording evidence; never promote a dataset or fabricate an SDK run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


FLAGS=('continuous_ok','sync_ok','completeness_ok','quality_ok','performance_ok','interaction_ok','lifecycle_ok')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def audit(directory,verify_files=True):
    directory=Path(directory).resolve()
    session=read(directory/'session.json')
    job=read(directory/'job_spec.json') if (directory/'job_spec.json').exists() else {}
    row={'directory':str(directory),'recording_id':session['recording_id'],'test_case':job.get('test_case'),
         'status':session['status'],'outcome':session['outcome'],'backend':session['backend'],
         'policy':session['policy'],'counts':session['counts'],'flags':session['acceptance_results'],
         'failure':session.get('failure'),'ready_exists':(directory/'READY').exists(),
         'ready_hash_ok':None,'files_verified':0,'integrity_errors':[]}
    for filename in ('capabilities.json','validation.json','performance.json','geometry_diagnostics.json','environment.json'):
        if (directory/filename).exists():
            row[filename]=read(directory/filename)
    if row['ready_exists']:
        manifest_path=directory/'dataset_manifest.json'
        row['ready_hash_ok']=(directory/'READY').read_bytes()==(sha(manifest_path)+'\n').encode('ascii')
        manifest=read(manifest_path)
        require=['requested','scheduled','validated','written','readback_verified']
        if session['status']!='READY' or session['outcome']!='completed' or not all(manifest[k] is True for k in ('sync_ok','completeness_ok','file_integrity_ok')):
            row['integrity_errors'].append('READY has no complete independent validation')
        if len({manifest['counts'][k] for k in require})!=1 or manifest['counts']['gap_groups']!=0:
            row['integrity_errors'].append('Strict-complete counts do not agree')
        if verify_files:
            for item in manifest['files']:
                path=(directory/item['path']).resolve()
                if directory not in path.parents or path.is_symlink() or not path.is_file():
                    row['integrity_errors'].append('Missing or unsafe manifest path: '+item['path'])
                elif path.stat().st_size!=item['size_bytes'] or sha(path)!=item['sha256']:
                    row['integrity_errors'].append('File hash or byte count differs: '+item['path'])
                else:
                    row['files_verified']+=1
        if not row['ready_hash_ok']:
            row['integrity_errors'].append('READY differs from actual manifest SHA256')
    elif session['status']=='READY':
        row['integrity_errors'].append('Session says READY but no discovery marker exists')
    if session['outcome'] in ('failed','stopped') and row['ready_exists']:
        row['integrity_errors'].append('Failed or stopped original recording must not be READY')
    row['data_accepted']=row['ready_exists'] and row['ready_hash_ok'] and not row['integrity_errors']
    row['full_project_accepted']=row['data_accepted'] and all(row['flags'].get(k) is True for k in FLAGS)
    return row


def summarize(rows):
    def case_pass(name,groups):
        matching=[r for r in rows if r['test_case']==name and r['data_accepted'] and r['counts']['readback_verified']>=groups and
                  (name!='M1_camera_static' or r.get('validation.json',{}).get('motion_evidence',{}).get('static_ok') is True)]
        return {'passed':bool(matching),'recordings':[r['recording_id'] for r in matching]}
    milestones={
        'M1_camera_static':case_pass('M1_camera_static',200),
        'M1_camera_moving':case_pass('M1_camera_moving',200),
        'M2_lidar':case_pass('M2_lidar_moving',200),
        'M2_mixed':case_pass('M2_mixed_moving',200),
        'M2_full':{'passed':False,'recordings':[]},
    }
    full=[r for r in rows if r['test_case'] in ('M2_full_moving','M2_full_barrier_retry') and r['data_accepted'] and r['counts']['readback_verified']>=100]
    milestones['M2_full']={'passed':bool(full),'recordings':[r['recording_id'] for r in full]}
    return {'schema_version':1,'scope':'existing actual evidence; no new engine, no READY mutation',
        'recordings':rows,'milestones':milestones,
        'accepted_recordings':sum(r['data_accepted'] for r in rows),
        'accepted_groups':sum(r['counts']['readback_verified'] for r in rows if r['data_accepted']),
        'all_ready_integrity_ok':all(not r['integrity_errors'] for r in rows),
        'full_project_accepted':any(r['full_project_accepted'] for r in rows),
        'unverified_requirements':['M3 native focus, reset, live mount revision and 20 cycles require their own evidence',
            'M4 fault scope is separate from READY data correctness',
            'M5 requires six alternating benchmark rounds, quality/control evidence and a 30 minute full-selection run']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path,help='Output root with datasets/failed/partial, or one recording directory')
    p.add_argument('--output',type=Path,required=True,help='External report path; cannot be inside an immutable dataset')
    p.add_argument('--metadata-only',action='store_true',help='Explicitly skip file SHA reads; cannot accept data')
    a=p.parse_args()
    folders=[a.root] if (a.root/'session.json').exists() else sorted({q.parent for kind in ('datasets','failed','partial') for q in (a.root/kind).glob('*/session.json')})
    rows=[]
    for folder in folders:
        if folder.resolve()==a.output.resolve().parent or folder.resolve() in a.output.resolve().parents:
            p.error('Report must be outside the recording; existing READY artifacts are immutable')
        try:
            row=audit(folder,not a.metadata_only)
            if a.metadata_only:
                row['data_accepted']=row['full_project_accepted']=False
            rows.append(row)
        except Exception as exc:
            rows.append({'directory':str(folder),'recording_id':folder.name,'test_case':None,'data_accepted':False,
                         'full_project_accepted':False,'integrity_errors':[type(exc).__name__+': '+str(exc)]})
    report=summarize(rows)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('recordings','unverified_requirements')},ensure_ascii=False))
    sys.exit(0 if report['all_ready_integrity_ok'] else 2)
