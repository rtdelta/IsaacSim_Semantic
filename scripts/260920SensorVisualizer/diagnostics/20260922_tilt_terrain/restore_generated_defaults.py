import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
p=root/'generated/sensors.json'
result={'changed':False}
if p.exists():
    data=json.loads(p.read_text());cfg=data['config']
    if cfg.get('ros_domain_id')==141 and 'reports/tilt_terrain/diagnostic_recordings' in cfg.get('output_directory',''):
        backup=root/'reports/tilt_terrain/diagnostic_generated_sensors.json'
        if not backup.exists():backup.write_bytes(p.read_bytes())
        defaults=json.loads((root/'config/sensors.json').read_text())
        cfg['ros_domain_id']=defaults['ros_domain_id'];cfg['output_directory']=defaults['output_directory']
        p.write_text(json.dumps(data,indent=2)+'\n')
        result={'changed':True,'ros_domain_id':cfg['ros_domain_id'],'output_directory':cfg['output_directory'],
                'note':'Runtime entry will rediscover sensors normally on the next launch'}
print(json.dumps(result))
