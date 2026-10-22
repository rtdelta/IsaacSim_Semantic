import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
latest=json.loads((root/'reports/latest_capture.json').read_text());capture=Path(latest['directory'])/'capture';result=json.loads((capture/'result.json').read_text());session=Path(result['capture']['session'])
code="""import json,rosbag2_py,sys
from pathlib import Path
r=rosbag2_py.SequentialReader();r.open(rosbag2_py.StorageOptions(uri=sys.argv[1],storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
m=r.get_metadata();value={'topics':[{'name':t.topic_metadata.name,'type':t.topic_metadata.type,'messages':t.message_count} for t in m.topics_with_message_count],'message_count':m.message_count,'file_names':m.relative_file_paths}
Path(sys.argv[2]).write_text(json.dumps(value,indent=2));print(json.dumps(value))
"""
p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec "$@"','inspect','/usr/bin/python3','-c',code,str(session/'bag_unified'),str(root/'reports/bag_topic_counts.json')],capture_output=True,text=True,timeout=20)
print(json.dumps({'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'capture_logs':[str(f.relative_to(capture)) for f in capture.glob('*')]}))
assert p.returncode==0
