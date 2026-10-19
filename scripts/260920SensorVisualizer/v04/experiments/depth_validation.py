"""ROS-side depth evidence: frozen repeat and independent analytic ray target."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.compare_mcap import read

def nearest(a,b):
    if not len(a) or not len(b): return None
    source=a[np.linspace(0,len(a)-1,min(len(a),10000),dtype=int)]
    d=cKDTree(b).query(source,workers=1)[0]
    return {'samples':len(source),'mean_m':float(d.mean()),'p95_m':float(np.quantile(d,.95)),
        'p99_m':float(np.quantile(d,.99)),'max_m':float(d.max())}

def frozen(out):
    info=json.loads((out/'frozen_repeat.json').read_text());a=np.load(out/'frozen_first.npz');b=np.load(out/'frozen_repeat.npz')
    result={'directory':str(out),'source_simulation_ns':info['simulation_ns'],'both_complete':info['both_complete'],
        'pose_matrix_max_difference':max(float(np.abs(np.asarray(info['first_lidars'][sid]['to_world'])-
            np.asarray(info['second_lidars'][sid]['to_world'])).max()) for sid in info['first_lidars']),
        'source_time_max_difference_s':max(abs(info['first_lidars'][sid]['source_time_s']-
            info['second_lidars'][sid]['source_time_s']) for sid in info['first_lidars']),'clouds':[]}
    for key in a.files:
        x,y=a[key],b[key]
        result['clouds'].append({'sensor':key,'first_points':len(x),'repeat_points':len(y),
            'identical':x.shape==y.shape and bool(np.array_equal(x,y)),
            'bidirectional_sampled_nearest':[nearest(x,y),nearest(y,x)]})
    return result

def analytic(out):
    box=json.loads((out/'analytic_box.json').read_text());low=np.asarray(box['min_world']);high=np.asarray(box['max_world'])
    session=Path(json.loads((out/'capture_result.json').read_text())['session']);groups=read(session);rows=[]
    for stamp,g in sorted(groups.items()):
        index=g['index'];group=index['group_id']
        for sid,meta in index['lidars'].items():
            xyz=g['/lidar/'+sid+'/points'].astype(float);m=np.asarray(meta['to_world'])
            world=xyz@m[:3,:3]+m[3,:3]
            surface=np.minimum(abs(world-low),abs(world-high)).min(axis=1)
            outside=np.maximum(np.maximum(low-world,world-high),0).max(axis=1)
            expected=85632 if sid.startswith('MyAiry') else 46080
            row={'group':group,'stamp_ns':stamp,'sensor':sid,'policy':'gated' if group<2 else 'keepalive',
                'points':len(xyz),'expected_rays':expected,'surface_max_error_m':float(surface.max()) if len(xyz) else None,
                'surface_p99_error_m':float(np.quantile(surface,.99)) if len(xyz) else None,
                'outside_max_m':float(outside.max()) if len(xyz) else None}
            row['passed']=len(xyz)==expected and row['surface_max_error_m']<.001 and row['outside_max_m']<.001
            rows.append(row)
    return {'directory':str(out),'session':str(session),'groups':len(groups),'clouds':rows,
        'passed':bool(rows) and all(r['passed'] for r in rows),
        'geometry_passed':bool(rows) and all(r['points']>0 and r['surface_max_error_m']<.001 and r['outside_max_m']<.001 for r in rows),
        'full_emitter_coverage_passed':bool(rows) and all(r['points']==r['expected_rays'] for r in rows),
        'coverage_note':'Configured emitter count is not a guarantee of a valid echo; retain the failed full-coverage assertion separately from geometry accuracy.',
        'tolerance_m':.001,'scope':'Opaque geometric reference with rangeAccuracyM=0 before products; diagnostic scene, excluded from throughput claims'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=('frozen','analytic'));parser.add_argument('directory');parser.add_argument('report')
    args=parser.parse_args();result=globals()[args.kind](Path(args.directory));Path(args.report).write_text(json.dumps(result,indent=2))
    print(json.dumps({'passed':result.get('passed'),'report':args.report}))
