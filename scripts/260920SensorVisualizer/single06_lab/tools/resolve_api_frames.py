"""Resolve sampled public NVRTC frames by exact exported ELF symbol intervals.

Counts sampled ancestry, not API invocations or exclusive execution time.
No guessed names for stripped private functions; no hooks or binary changes.
"""
import argparse,collections,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.analysis import load_rows

def resolve(directory,catalog_path):
 directory=Path(directory);catalog=json.loads(Path(catalog_path).read_text())['modules']
 maps=[r for r in load_rows(directory) if r['event']=='lab_module_mapping' and 'libnvrtc' in r['module']]
 intervals=[];unmapped=[]
 for m in maps:
  cat=next((c for c in catalog if m['module'] in (c['path'],c['resolved_path'])),None)
  if not cat:unmapped.append(m['module']);continue
  page=4096;segment=next((s for s in cat.get('load_segments',[]) if s['file_offset']//page*page==m['file_offset']),None)
  if not segment:continue
  bias=m['start_address']-segment['virtual_address']//page*page
  for symbol in cat['symbols']:
   start=bias+symbol['address'];end=start+symbol['size']
   if symbol['size']>0:intervals.append((start,end,symbol['name']))
 with sqlite3.connect(directory/'native.sqlite') as db:
  ranges=db.execute("SELECT n.start,n.end,n.globalTid FROM NVTX_EVENTS n LEFT JOIN StringIds s ON s.id=n.textId WHERE COALESCE(n.text,s.value)='SL06_WINDOW' AND n.end>n.start").fetchall()
  if not ranges:raise RuntimeError('No closed native window')
  start,end,tid=ranges[0];counts=collections.defaultdict(set);leaf=collections.defaultdict(set);sample_frames=collections.defaultdict(list)
  samples=db.execute('''SELECT e.id,c.stackDepth,c.originalIP,m.value,s.value FROM COMPOSITE_EVENTS e
   JOIN SAMPLING_CALLCHAINS c ON c.id=e.id LEFT JOIN StringIds m ON m.id=c.module
   LEFT JOIN StringIds s ON s.id=c.symbol WHERE e.globalTid=? AND e.start BETWEEN ? AND ?''',(tid,start,end))
  total=set()
  for sample,depth,ip,module,symbol in samples:
   total.add(sample)
   sample_frames[sample].append({'depth':depth,'module':module,'exported_or_unresolved_symbol':symbol})
   if ip is None:continue
   for a,b,name in intervals:
    if a<=ip<b:
     counts[name].add(sample)
     if depth==0:leaf[name].add(sample)
  matching=set().union(*counts.values()) if counts else set()
  caller_samples=collections.Counter()
  for sample in matching:
   for module in {r['module'] for r in sample_frames[sample] if r['module'] and 'libnvrtc' not in r['module']}:
    caller_samples[module]+=1
  out={'available':bool(intervals),'main_thread_samples':len(total),'mapped_intervals':len(set(intervals)),
    'sampled_public_api_ancestry':{n:len(s) for n,s in counts.items()},
    'sampled_public_api_leaf':{n:len(s) for n,s in leaf.items()},'unmapped_modules':sorted(set(unmapped)),
    'module_ancestry_in_public_api_samples':dict(caller_samples.most_common()),
    'example_sample_stacks':[sorted(sample_frames[s],key=lambda r:r['depth']) for s in sorted(matching)[:3]],
    'limits':['Exact ELF symbol-size intervals and PT_LOAD address mapping only.',
      'Ancestry sample counts are not invocation counts or exclusive CPU durations.',
      'No public frame match does not prove no JIT compilation; private symbols and unwind gaps remain.']}
 (directory/'public_api_frames.json').write_text(json.dumps(out,indent=2));return out

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--catalog',required=True);a=p.parse_args()
 print(json.dumps(resolve(a.directory,a.catalog),indent=2))
