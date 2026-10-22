import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/native_rotation_localization/native007_20261015_v1')
out=[]
for p in sorted(root.glob('*/*/*/*/analysis/summary.json')):
 d=json.loads(p.read_text());s=d['spec'];m=d['first_target']
 out.append({'condition':s['condition'],'profile':s['profile'],'repeat':s['repeat'],'run_id':s['run_id'],'N':d['planned_targets'],
  'qualified':d['measurement_qualified'],'cleanup':d['cleanup_ok'],'distance_fail':d['distance_failed'],'direction_fail':d['direction_failed'],
  'absolute_fail':d['geometry_absolute_failed'],'increment_fail':d['geometry_increment_failed'],'native_pose_fail':d['native_pose_failed'],'candidates':d['candidate_counts'],
  'first_plane_p95_m':m.get('geometry',{}).get('point_plane_m',{}).get('0.95'),'first_yaw_rad':m.get('geometry',{}).get('yaw_error_rad'),
  'first_distance_p95_m':m.get('ray_residual_m',{}).get('0.95'),'readback_errors':d['readback']['errors'][:2],'official_parser':d['official_parser_crosscheck'],
  'api_polls':d['api_polls'],'api_unique':d['api_unique_identities']})
print(json.dumps(out))
