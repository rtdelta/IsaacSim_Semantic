import subprocess
script = """import json, rosbag2_py, PIL, numpy
print(json.dumps({'writer':dir(rosbag2_py.SequentialWriter), 'storage':rosbag2_py.StorageOptions.__init__.__doc__, 'topic':rosbag2_py.TopicMetadata.__init__.__doc__, 'pillow':PIL.__version__, 'numpy':numpy.__version__}))
"""
run = subprocess.run(['/bin/bash','--noprofile','--norc','-c',
                      'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -c "$1"',
                      'sv02-api', script], text=True, capture_output=True, timeout=20)
print(run.stdout)
print(run.stderr)
raise SystemExit(run.returncode)
