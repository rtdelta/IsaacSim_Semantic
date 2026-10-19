"""Summarize all paired targets and fixed-index independent F/F RGB variability."""
import json
from pathlib import Path
import numpy as np
from tools.experiments.storage import rows,save,digest
from tools.experiments.compare_paired_outputs import payload,quantiles
ROOT=Path(__file__).resolve().parents[2]
directory=ROOT/'reports/remote/reports/paired_delivery_evidence/paired_20261014_e1_scene18_mixed'
manifest=json.loads((directory/'delivery_manifest.json').read_text())
for item in manifest['files']:
    p=directory/item['path']
    if p.stat().st_size!=item['bytes'] or digest(p)!=item['sha256']:raise ValueError('Delivery mismatch '+str(p))
summary=[];reference=None;variation=[]
for repeat in ('r01','r02','r03'):
    parent=directory/'repeats'/repeat
    s=json.loads((parent/'analysis/summary.json').read_text())
    m=[json.loads(line) for line in (parent/'analysis/paired_metrics.jsonl').read_text().splitlines()]
    mechanism=json.loads((parent/'analysis/mechanism_relations.json').read_text())
    summary.append({'repeat':repeat,'summary':s,'lidar_bad':{side:sum(not r[side+'_native_pose_pass'] for r in m if r['kind']=='lidar') for side in ('C','F')},
        'gmo_independent_equal':{side:mechanism[side]['all_decoded_valid_xyz_equal_extractor'] for side in ('continuous','frozen_v06')}})
    folder=parent/'frozen_v06';events=rows(folder/'native_events.jsonl');applied={r['target_index']:r for r in rows(folder/'applied_states.jsonl')}
    selected={r['target_index']:r for r in events if r['kind']=='camera' and r['target_index'] in (0,50,99)}
    if reference is None:reference=(folder,selected,applied);continue
    for index,row in selected.items():
        old=reference[1][index];a=payload(reference[0],old).astype(float);b=payload(folder,row).astype(float)
        matrix_delta=float(np.max(np.abs(np.array(row['historical_to_world'])-np.array(old['historical_to_world']))))
        root_delta=float(np.max(np.abs(np.array(applied[index]['actual']['root_position'])-np.array(reference[2][index]['actual']['root_position']))))
        delta=a-b;mse=float(np.mean(delta**2))
        variation.append({'repeat':repeat,'reference':'r01','target_index':index,'sensor_matrix_max_abs_delta':matrix_delta,
            'root_position_max_abs_delta_m':root_delta,'image_mae':float(np.mean(np.abs(delta))),'image_psnr_db':float(10*np.log10(255**2/mse)) if mse else None})
result={'schema_version':1,'scope':'E1 selected mixed block; all 300 lidar pairs; F/F image baseline uses predeclared first/middle/last across independent initializations',
    'delivery_files_verified':len(manifest['files']),'runs':summary,'camera_lighting_equivalence':False,
    'camera_lighting_reason':'Original C preserves two DomeLights; original F explicitly selects one; pose equivalence is insufficient for image attribution',
    'fixed_F_F_images':variation,'F_F_mae':quantiles([x['image_mae'] for x in variation]),'F_F_psnr_db':quantiles([x['image_psnr_db'] for x in variation])}
save(ROOT/'reports/paired_e1_aggregate.json',result)
print(json.dumps({'verified_files':len(manifest['files']),'runs':[(r['repeat'],r['lidar_bad']) for r in summary],'F_F_mae':result['F_F_mae'],'F_F_psnr_db':result['F_F_psnr_db']}))
