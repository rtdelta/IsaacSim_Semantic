"""Local evidence reduction and standalone native timeline figure."""
from pathlib import Path
import json,statistics
ROOT=Path(__file__).resolve().parents[1];REPORTS=ROOT/'reports'
def load(name):return json.loads((REPORTS/name).read_text(encoding='utf-8'))
def dist(values):
    v=sorted(values)
    return {'count':len(v),'p50':statistics.median(v),'p95':v[min(len(v)-1,int(len(v)*.95))],'mean':statistics.mean(v),'max':v[-1]} if v else None
data={}
for name in ('baseline','primed','shared','persistent_gated','production','final_baseline','final_gated','final_throughput'):
    if not (REPORTS/(name+'.json')).exists():continue
    src=load(name+'.json');result=src.get('capture_result.json',{}).get('status',{})
    groups=[(g['ticket_complete_ns']-g['start_ns'])/1e9 for d in src.get('diagnostics',[]) for g in d['groups'].values()
            if 'ticket_complete_ns' in g and 'start_ns' in g]
    resources=[r for d in src.get('diagnostics',[]) for r in d['resources']]
    data[name]={'directory':src['directory'],'result':result,'group_to_owned_s':dist(groups),
        'spans':[r for d in src.get('diagnostics',[]) for r in d['spans']],
        'resources':resources,'retry_count':sum(len(d['retries']) for d in src.get('diagnostics',[])),
        'error_lines':src.get('errors',[]),'supervisor':src.get('supervisor_result.json')}
(REPORTS/'performance_metrics.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
native=load('native_analysis.json')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(2,1,figsize=(13,6),sharex=True,layout='constrained')
b=native['bins'];t=[x['offset_s'] for x in b]
axes[0].step(t,[x['main_scheduled_s']/x['wall_s']*100 for x in b],where='post',label='Main thread scheduled CPU',color='#d45b29')
axes[1].step(t,[x['gpu_union_s']/x['wall_s']*100 for x in b],where='post',label='Observed GPU intervals (incomplete trace)',color='#178978')
origin=next(x for x in native['zones'] if x['label']=='SV04_PROFILE')['start']
for z in native['ranges']:
    if z['duration_s']<2:continue
    a,b0=(z['start']-origin)/1e9,(z['end']-origin)/1e9
    for ax in axes:ax.axvspan(a,b0,alpha=.12,color='#cf5136')
    axes[0].text((a+b0)/2,107,z['label'].split()[-1]+' init',ha='center',fontsize=9)
for ax in axes:
    ax.set_ylim(0,120);ax.set_ylabel('Interval coverage (%)');ax.grid(alpha=.2);ax.legend(loc='lower left')
axes[1].set_xlabel('Seconds from native capture window start (200 ms bins)')
fig.suptitle('v03 native thread schedule and recorded GPU work\nGPU coverage is a lower bound: individual Vulkan trace overflowed')
fig.savefig(REPORTS/'native_timeline.png',dpi=140);plt.close(fig)
print(json.dumps({n:{'wall_capture_s':d['result'].get('wall_capture_s'),'group_to_owned_s':d['group_to_owned_s']} for n,d in data.items()},indent=2))
