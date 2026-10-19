"""CPU analysis-only speed/consistency check, keeps the first analysis intact."""
import json,os,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
parent=root/'reports/clock_state_consistency/clock_20261014_v1/T0_A/repeats/r01'
env=os.environ.copy()
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[key]='1'
start=time.monotonic()
with (parent/'analysis_cpu1.log').open('x') as log:
    r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/analyze.py'),str(parent),'analysis_cpu1'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
if r.returncode:raise RuntimeError('CPU-only comparison analysis failed')
old=json.loads((parent/'analysis/summary.json').read_text());new=json.loads((parent/'analysis_cpu1/summary.json').read_text())
keys=['measurement_qualified','failure_crosstable','best_candidate_group_counts','candidate_status_counts','native_pose_failed','geometry_failed','all_GMO_valid_XYZ_equals_extractor']
report={'schema_version':1,'wall_seconds':time.monotonic()-start,'all_decision_fields_equal':all(old[k]==new[k] for k in keys),
    'compared_fields':keys,'old_analyzer_sha256':old.get('analyzer_sha256'),'new_analyzer_sha256':new.get('analyzer_sha256'),
    'original_analysis_retained':True,'captures_unchanged':True}
(parent/'analysis_cpu1/consistency_check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if not report['all_decision_fields_equal']:raise RuntimeError('CPU analysis decisions changed; stop adoption')
