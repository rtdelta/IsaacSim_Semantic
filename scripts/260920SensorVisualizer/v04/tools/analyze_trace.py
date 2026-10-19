"""Usage: python tools/analyze_trace.py RUN/diagnostics --trace [--compare OTHER]."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v04.analysis import analyze,compare_manifests

def main():
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--trace',action='store_true');p.add_argument('--compare')
    a=p.parse_args();result=analyze(a.directory,a.trace)
    print(json.dumps({'stages':len(result['stages']),'retries':result['retries'],
                      'log_quality':result['log_quality'],'unclosed_spans':result['unclosed_spans']},indent=2))
    if a.compare:print(json.dumps(compare_manifests(a.directory,a.compare),indent=2))
    print(str(Path(a.directory)/'analysis.json'))

if __name__=='__main__':main()
