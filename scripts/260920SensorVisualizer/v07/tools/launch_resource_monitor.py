"""Observe only the recorded launch PID through exec and stop when it exits."""
import argparse
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sensor_visualizer_v07.contracts import load_job
from sensor_visualizer_v07.diagnostics import RunDiagnostics

def ticks(pid):
    try:
        fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
        return None if fields[0] in ('Z','X') else fields[19]
    except (OSError,IndexError):return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--ticks',required=True)
    p.add_argument('--directory',required=True);p.add_argument('--role',required=True);args=p.parse_args()
    diag=RunDiagnostics(str(ROOT),load_job()['diagnostics'],ROOT,role='launch_monitor',directory=args.directory)
    diag.context(watched_pid=args.pid,launch_role=args.role,phase='engine_process_lifetime')
    diag.start_resources();diag.sampler.pids['kit_launch']=args.pid
    try:
        while ticks(args.pid)==args.ticks:time.sleep(.25)
        diag.event('watched_launch_exited',critical=True)
    finally:diag.close()

if __name__=='__main__':main()
