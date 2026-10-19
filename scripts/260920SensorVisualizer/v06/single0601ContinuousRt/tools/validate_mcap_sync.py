"""Run in a separate process with the installed ROS 2 Jazzy environment."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from single0601_continuous_rt.validation import validate_recording

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory')
    args=parser.parse_args()
    report, segments=validate_recording(args.directory)
    print(json.dumps({k:report[k] for k in ('sync_ok','completeness_ok','file_integrity_ok','counts','errors')}))
    raise SystemExit(0 if report['sync_ok'] and report['file_integrity_ok'] else 2)
