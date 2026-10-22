import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.analysis import analyze
p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args()
r=analyze(a.directory)
print(json.dumps({'directory':r['directory'],'events':sum(r['event_counts'].values()),
 'native_available':r['native']['available'],'buffer_contract':r['buffer_contract']},indent=2))
