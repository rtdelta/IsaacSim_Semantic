import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/output/native_capture_baseline')
p=root/'smoke_20261011_124719'
d=json.loads((p/'validation.json').read_text());m=json.loads((p/'sensor_manifest.json').read_text())
print(json.dumps({'topics':d['topics'],'tf_final_comparison':d['tf_final_comparison'],
 'common_stamps':d['all_sensor_common_stamps'],'measurement_topic_counts':d['measurement_topic_counts'],
 'parameters':[{s['id']:s.get('parameters')} for s in m['sensors'] if s['kind']=='lidar'],
 'first_images':[str(f) for f in p.glob('*first.png')]}))
