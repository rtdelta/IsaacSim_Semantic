"""Local static plots from original 1 Hz evidence; no additional cloud sampling."""
import json,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze_suite import resource_samples,read,LABELS

root=Path(sys.argv[1]);out=root/'analysis';out.mkdir(exist_ok=True)
result=read(out/'comparison.json');paths=[]
for repeat in sorted({c['round'] for c in result['cases']}):
 members={c['id']:c for c in result['cases'] if c['round']==repeat}
 fig,axes=plt.subplots(4,2,figsize=(17,13),layout='constrained')
 for ax,(cid,label) in zip(axes.flat,LABELS.items()):
  c=members.get(cid);ax.set_title(cid+' | '+label,fontsize=10);ax.set_xlabel('wall seconds from first measured group');ax.set_ylim(0,105);ax.set_ylabel('whole-GPU busy (%)');ax.grid(alpha=.2)
  if not c:continue
  case=root/cid/f'round_{repeat:02d}';timing=read(case/'timing.json');groups=timing['groups']
  if not groups:continue
  begin=groups[0]['start_ns'];end=groups[-1]['end_ns'];samples=[s for s in resource_samples(case/'capture',c['config']['family']=='v06') if begin<=s['t']<=end]
  xs=[(s['t']-begin)/1e9 for s in samples]
  ax.plot(xs,[s['gpu_percent'] for s in samples],marker='.',color='#167ab5',label='GPU busy')
  for i,g in enumerate(groups):
   a=(g['start_ns']-begin)/1e9;b=(g['end_ns']-begin)/1e9;ax.axvspan(a,b,color='#3c8a58' if i%2==0 else '#789090',alpha=.07);ax.axvline(a,color='#8d939b',linewidth=.5)
  cpu=ax.twinx();cpu.plot(xs,[s['kit_cpu_percent'] if s.get('kit_cpu_percent_interval_begin') is not None and s['kit_cpu_percent_interval_begin']>=begin else None for s in samples],color='#c8612e',alpha=.85,label='Kit CPU');cpu.set_ylim(bottom=0);cpu.set_ylabel('Kit CPU (100%=one core)',fontsize=9)
  ax.set_xlim(0,(end-begin)/1e9)
  if samples:
   handles,labels=ax.get_legend_handles_labels();hh,ll=cpu.get_legend_handles_labels();ax.legend(handles+hh,labels+ll,fontsize=8,loc='upper right')
  if len(samples)<4:ax.text(.03,.05,f'Only {len(samples)} in-window samples; trend unresolved',transform=ax.transAxes,color='#b00020',fontsize=9)
 fig.suptitle(f'NC-004 round {repeat}: original ~1 Hz device/process samples; shaded logical groups',fontsize=15)
 p=out/f'resources_round_{repeat:02d}.png';fig.savefig(p,dpi=130);plt.close(fig);paths.append(p.name)

report=out/'NC-004_report.md'
if report.exists():
 text=report.read_text(encoding='utf-8');marker='\n## Resource timeline figures\n'
 if marker in text:text=text.split(marker)[0]
 text+=marker+'\nApproximate 1 Hz evidence. GPU busy is not SM occupancy; CPU is Kit only. Continuous PT group ranges may overlap. Short windows cannot resolve stage-specific utilization.\n\n'+'\n\n'.join(f'![{p}]({p})' for p in paths)+'\n'
 report.write_text(text,encoding='utf-8')
print(json.dumps({'figures':paths}))
