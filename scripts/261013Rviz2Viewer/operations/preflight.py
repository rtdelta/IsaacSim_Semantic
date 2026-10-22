"""Read only the authorized single-instance project prerequisites."""
import hashlib, json, shutil, subprocess
from pathlib import Path

scene = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
source = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/lidar_equivalence_006/legacy')
native = Path('/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300')
kit = []
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        args = p.read_bytes().split(b'\0')
        if args and args[0].endswith(b'/kit/kit'):
            kit.append({'pid': int(p.parent.name), 'executable': args[0].decode(errors='replace')})
    except OSError:
        pass
gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader'], capture_output=True, text=True, timeout=15)
ros = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c', 'source /opt/ros/jazzy/setup.bash && exec "$@"', 'probe', '/usr/bin/python3', '-c', "import rosbag2_py,rclpy,numpy; from visualization_msgs.msg import MarkerArray; print('existing ROS viewer dependencies available')"], capture_output=True, text=True, timeout=20)
print(json.dumps({'scene': str(scene), 'scene_sha256': hashlib.sha256(scene.read_bytes()).hexdigest(), 'source_present': source.is_dir(), 'native_delivery_present': native.is_dir(), 'disk_free_gib': shutil.disk_usage(scene.parent).free/1024**3, 'kit_processes': kit, 'gpu': gpu.stdout.strip(), 'ros_exit': ros.returncode, 'ros_stdout': ros.stdout.strip(), 'ros_stderr': ros.stderr[-1000:]}))
