import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
rows=[]
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        raw=path.read_bytes()
        if b'/kit/kit' not in raw:continue
        pid=path.parent.name
        stat=(path.parent/'stat').read_text().rsplit(')',1)[1].split()
        tasks=[]
        for p in (path.parent/'task').glob('[0-9]*'):
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            tasks.append({'tid':int(p.name),'name':(p/'comm').read_text().strip(),
                          'cpu_ticks':int(fields[11])+int(fields[12]),'state':fields[0],'wait':(p/'wchan').read_text().strip()})
        rows.append({'pid':int(pid),'cpu_ticks':int(stat[11])+int(stat[12]),'main_wait':(path.parent/'wchan').read_text(),
                     'top_threads':sorted(tasks,key=lambda x:x['cpu_ticks'],reverse=True)[:12],'threads':len(tasks)})
    except (OSError,ValueError):pass
audio=Path('/root/isaacsim/exts/isaacsim.app.setup/isaacsim/app/setup/extension.py')
snippets=[]
if audio.is_file():
    lines=audio.read_text(errors='replace').splitlines()
    for i,line in enumerate(lines):
        if any(word in line.lower() for word in ('eula','license','audio','on_startup')):
            snippets.append('\n'.join(lines[max(0,i-2):i+6]))
gpu=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
print(json.dumps({'owned_kit':rows,'gpu':gpu.stdout,'cpu_stat':Path('/sys/fs/cgroup/cpu.stat').read_text(),'sdk_setup_snippets':snippets[:15]}))
