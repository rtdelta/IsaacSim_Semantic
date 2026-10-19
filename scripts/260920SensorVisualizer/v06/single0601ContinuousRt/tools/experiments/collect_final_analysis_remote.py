"""Read completed outputs and copy bounded metadata/figures inputs, no raw mutation."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
SOURCE=ROOT/'reports/paired_capture_experiments'
TARGET=ROOT/'reports/paired_analysis_evidence_20261014'
if TARGET.exists():raise RuntimeError('Refuse overwriting evidence collection')
TARGET.mkdir();copied=[];runs=[]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def copy(path):
    rel=path.relative_to(SOURCE);out=TARGET/rel;out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,out);h=sha(path)
    if sha(out)!=h:raise RuntimeError('Copy mismatch')
    copied.append({'path':rel.as_posix(),'sha256':h,'bytes':out.stat().st_size,'source':str(path)})
for experiment in ('paired_20261014_e0_room','paired_20261014_e2_room_mixed','paired_20261014_e0_scene18_lighting'):
    for repeat in sorted((SOURCE/experiment/'repeats').glob('*')):
        status=json.loads((repeat/'coordinator_status.json').read_text())
        if status['state'] not in ('COMPLETE','FAILED'):raise RuntimeError('Still running '+str(repeat))
        for p in repeat.glob('*.json'):copy(p)
        for p in (repeat/'analysis').glob('*'):
            if p.is_file():copy(p)
        for side in ('continuous','frozen_room','frozen_v06'):
            directory=repeat/side
            for p in directory.glob('*'):
                if p.is_file() and p.suffix in ('.json','.jsonl') and p.name!='sensor_registry.json':copy(p)
            if 'lighting' in experiment and (directory/'native_events.jsonl').exists():
                for line in (directory/'native_events.jsonl').read_text().splitlines():
                    row=json.loads(line)['data']
                    if row['kind']=='camera' and row['target_index']==6:copy(directory/row['payload_path'])
        record={'experiment':experiment,'repeat':repeat.name,'coordinator':status}
        if (repeat/'analysis/summary.json').exists():record['summary']=json.loads((repeat/'analysis/summary.json').read_text())
        if (repeat/'analysis/geometry_metrics.jsonl').exists():
            geo=[json.loads(line) for line in (repeat/'analysis/geometry_metrics.jsonl').read_text().splitlines()]
            metrics=[json.loads(line) for line in (repeat/'analysis/paired_metrics.jsonl').read_text().splitlines()]
            record['geometry_counts']={side:{'plane_bad':sum(not g[side]['passes_5mm'] for g in geo),'yaw_bad':sum(not g[side]['passes_observable_yaw'] for g in geo)} for side in ('C','F')} if geo else None
            by_index={m['target_index']:m for m in metrics}
            record['C_native_pass_but_yaw_bad']=sum(by_index[g['target_index']]['C_native_pose_pass'] and not g['C']['passes_observable_yaw'] for g in geo) if geo else None
        mechanism=repeat/'analysis/mechanism_relations.json'
        if mechanism.exists():
            data=json.loads(mechanism.read_text());record['gmo']={}
            for side,value in data.items():
                if not isinstance(value,dict) or 'groups' not in value:continue
                groups=value['groups'];classified=[]
                for g in groups:
                    if 'nominal_ray_actual_pose_range_residual_m' not in g:continue
                    residuals={'current_actual':g['nominal_ray_actual_pose_range_residual_m']['0.95']}
                    residuals.update({k:v['0.95'] for k,v in g['candidate_pose_range_residual_m'].items() if k.endswith('_SYNTHETIC')})
                    best=min(residuals,key=residuals.get)
                    classified.append({'target_index':g['target_index'],'best':best,'best_p95_m':residuals[best],'current_p95_m':residuals['current_actual']})
                record['gmo'][side]={'decoded_count':len(groups),'all_equal_extractor':value['all_decoded_valid_xyz_equal_extractor'],
                    'candidate_counts':{name:sum(c['best']==name for c in classified) for name in sorted({c['best'] for c in classified})},
                    'max_best_candidate_p95_m':max((c['best_p95_m'] for c in classified),default=None),
                    'max_current_pose_p95_m':max((c['current_p95_m'] for c in classified),default=None),'classified':classified}
        runs.append(record)
value={'schema_version':1,'scope':'bounded analysis and all metadata except bulky sensor registries; fixed target6 RGB for aligned lighting; all original raw bytes remain at remote source',
    'source':str(SOURCE),'runs':runs,'files':copied,'bytes':sum(p['bytes'] for p in copied)}
(TARGET/'analysis_manifest.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'directory':str(TARGET),'files':len(copied),'bytes':value['bytes'],
    'runs':[dict(experiment=r['experiment'],repeat=r['repeat'],state=r['coordinator']['state'],geometry_counts=r.get('geometry_counts')) for r in runs]}))
