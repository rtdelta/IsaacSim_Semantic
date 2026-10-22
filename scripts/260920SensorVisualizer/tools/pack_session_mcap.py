"""Run with system ROS Python after sourcing /opt/ros/jazzy/setup.bash."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer.unified_bag import assemble

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Create a verified unified MCAP from a finished session')
    parser.add_argument('session',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=assemble(args.session,args.output)
    print(json.dumps({k:report[k] for k in ('state','output','groups','image_counts','elapsed_s')},ensure_ascii=False))
