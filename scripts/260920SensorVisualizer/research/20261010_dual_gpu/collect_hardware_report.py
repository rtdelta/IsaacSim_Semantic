import json
from pathlib import Path
root=Path(__file__).resolve().parent
audit=Path('C:/Users/15452/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/CloudInstanceOps/audit/20261010/20261010T065759Z_a349732b6bd1.jsonl')
reports=[]
def inspect(value):
    if isinstance(value,dict):
        for v in value.values():inspect(v)
    elif isinstance(value,list):
        for v in value:inspect(v)
    elif isinstance(value,str) and value.startswith('{"utc":'):
        row=json.loads(value)
        if 'gpu_topology' in row.get('commands',{}):reports.append(row)
for line in audit.read_text(encoding='utf-8').splitlines():inspect(json.loads(line))
assert len(reports)==1,len(reports)
row=reports[0];(root/'hardware_report.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
cpu=json.loads(row['commands']['lscpu']['stdout'])['lscpu']
selected={x['field']:x['data'] for x in cpu if x['field'] in ('CPU(s):','Model name:','NUMA node(s):','NUMA node0 CPU(s):','NUMA node1 CPU(s):','Socket(s):','Thread(s) per core:')}
small={'cpu':selected,'affinity_count':len(row['cpu_affinity']),'affinity':row['cpu_affinity'],'cgroup':row['cgroup'],
       'meminfo':row['meminfo'],'disk':row['disk'],'tools':row['tools'],'code_diff':row['v06_code_diff'],
       'processes':[{k:v for k,v in p.items() if k!='status'}|{'status':{s.split(':')[0]:s.split(':',1)[1].strip() for s in p['status'].splitlines() if s.startswith(('Threads:','VmRSS:','Cpus_allowed_list:','Mems_allowed_list:'))}} for p in row['relevant_processes']],
       'commands':{k:v for k,v in row['commands'].items() if k not in ('lscpu','gpu_pcie')},
       'pcie': '\n'.join(s for s in row['commands']['gpu_pcie'].get('stdout','').splitlines() if any(x in s for x in ('Bus Id','Link Width','Link Generation','Device Current','Device Max','Current','Max','Replay')))}
print(json.dumps(small,ensure_ascii=False,indent=2))
