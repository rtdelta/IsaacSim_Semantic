"""Bounded read-only resource sampling; no imports from the remote project."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

HZ=os.sysconf('SC_CLK_TCK'); PAGE=os.sysconf('SC_PAGE_SIZE')
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')

def read(path):
    try: return Path(path).read_text()
    except (OSError,UnicodeError): return ''

def command(args,timeout=5):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return dict(exit=r.returncode,stdout=r.stdout.strip(),stderr=r.stderr.strip())
    except Exception as e: return dict(error=type(e).__name__)

def stat(path):
    v=read(path)
    if not v:return None
    at=v.rfind(')'); name=v[v.find('(')+1:at]; fields=v[at+2:].split()
    return dict(name=name,state=fields[0],ticks=int(fields[11])+int(fields[12]),
                start=int(fields[19]),rss=int(fields[21])*PAGE,threads=int(fields[17]))

def classify(folder,name):
    raw=(folder/'cmdline').read_bytes().split(b'\0')
    parts=[v.decode(errors='replace') for v in raw]
    joined=' '.join(parts)
    if '/kit/kit' in joined or name=='kit': return 'Isaac Kit'
    if 'rviz2' in joined:return 'RViz2'
    if ('ros2' in joined and 'record' in parts) or 'rosbag2_transport' in joined:return 'ROS bag recorder'
    if any(v in joined for v in ('Xvnc','Xtigervnc','Xorg','xfwm4','novnc','websockify')):return 'Desktop/'+name
    if 'launch_isaac.py' in joined:return 'Isaac launcher'
    return name

def processes():
    result={}
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():continue
        try:
            s=stat(folder/'stat')
            if s is None:continue
            s['pid']=int(folder.name);s['label']=classify(folder,s['name'])
            io={k:int(v) for k,v in (line.split(':',1) for line in read(folder/'io').splitlines())}
            s['read_bytes']=io.get('read_bytes',0);s['write_bytes']=io.get('write_bytes',0)
            s['wchan']=read(folder/'wchan').strip()
            if s['label']=='Isaac Kit':
                s['thread_stats']={d.name:stat(d/'stat') for d in (folder/'task').iterdir()}
            result[s['pid']]=s
        except (OSError,ValueError,IndexError):pass
    return result

def host():
    mem={k:int(v.split()[0]) for k,v in (l.split(':',1) for l in read('/proc/meminfo').splitlines())}
    cpu=[int(v) for v in read('/proc/stat').splitlines()[0].split()[1:9]]
    vm={k:int(v) for k,v in (l.split() for l in read('/proc/vmstat').splitlines()) if k in ('pswpin','pswpout','pgmajfault')}
    return dict(cpu=cpu,mem_total_kb=mem.get('MemTotal'),mem_available_kb=mem.get('MemAvailable'),
                swap_total_kb=mem.get('SwapTotal'),swap_free_kb=mem.get('SwapFree'),vm=vm,
                loadavg=read('/proc/loadavg').strip(),pressure={n:read('/proc/pressure/'+n).strip() for n in ('cpu','memory','io')})

def cgroup():
    base=Path('/sys/fs/cgroup')
    values={n:read(base/n).strip() for n in ('cpu.max','cpu.stat','cpuset.cpus.effective','memory.current','memory.max','memory.events','memory.swap.current','io.stat','cpu.pressure','memory.pressure','io.pressure')}
    if not values['cpu.max']:
        values.update({n:read(base/n).strip() for n in ('cpu/cpu.cfs_quota_us','cpu/cpu.cfs_period_us','cpu/cpu.stat','cpuset/cpuset.cpus','memory/memory.usage_in_bytes','memory/memory.limit_in_bytes','memory/memory.failcnt')})
    return values

def gpu():
    return command(['nvidia-smi','--query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory','--format=csv,noheader,nounits'])

def gpu_processes():
    result=command(['nvidia-smi','-q','-x'])
    if result.get('exit')!=0:return result
    try:
        root=ET.fromstring(result['stdout']); rows=[]
        for g in root.findall('gpu'):
            for p in g.findall('./processes/process_info'):
                pid=p.findtext('pid');rows.append(dict(pid=pid,type=p.findtext('type'),name=Path(p.findtext('process_name') or '').name,
                    used_memory=p.findtext('used_memory'),visible_in_container=bool(pid and Path('/proc',pid).exists())))
        return rows
    except ET.ParseError:return dict(error='XML parse failed')

def storage():
    d=shutil.disk_usage('/root/gpufree-data')
    rows=[]
    root=Path('/root/gpufree-data/semantic/output/sensor_visualizer')
    if root.exists():
        dirs=sorted((p for p in root.iterdir() if p.is_dir() and p.name!='camera_snapshots'),key=lambda p:p.stat().st_mtime,reverse=True)[:2]
        for folder in dirs:
            files=[]
            for p in folder.glob('bag/*'):
                if p.is_file():files.append(dict(name=p.name,bytes=p.stat().st_size,mtime=p.stat().st_mtime))
            cameras=[]
            for p in folder.glob('cameras/*/frames.jsonl'):
                cameras.append(dict(id=p.parent.name,bytes=p.stat().st_size,mtime=p.stat().st_mtime))
            rows.append(dict(session=folder.name,bag=files,cameras=cameras,summary=(folder/'summary.json').exists()))
    return dict(total_bytes=d.total,free_bytes=d.free,sessions=rows)

report=dict(start_utc=datetime.now(timezone.utc).isoformat(),clock_ticks=HZ,logical_cpus=os.cpu_count(),
            affinity_cpus=len(os.sched_getaffinity(0)),cgroup_start=cgroup(),host_start=host(),
            gpu_processes_start=gpu_processes(),pmon_start=command(['nvidia-smi','pmon','-c','1','-s','um']),
            storage_start=storage(),samples=[])
before=processes();before_time=time.monotonic();before_host=host()
for _ in range(6):
    time.sleep(4)
    now_time=time.monotonic();dt=now_time-before_time;now=processes();now_host=host()
    rows=[]
    for pid,s in now.items():
        b=before.get(pid)
        if not b or s['start']!=b['start']:continue
        row={k:s[k] for k in ('pid','label','state','threads','wchan')}
        row.update(cpu_one_core_percent=round((s['ticks']-b['ticks'])/HZ/dt*100,2),rss_mib=round(s['rss']/2**20,1),
                   read_mib_s=round((s['read_bytes']-b['read_bytes'])/dt/2**20,3),write_mib_s=round((s['write_bytes']-b['write_bytes'])/dt/2**20,3))
        if s['label']=='Isaac Kit':
            threads=[]
            for tid,t in s.get('thread_stats',{}).items():
                bt=b.get('thread_stats',{}).get(tid)
                if t and bt and t['start']==bt['start']:
                    threads.append(dict(tid=int(tid),name=t['name'],state=t['state'],cpu_percent=round((t['ticks']-bt['ticks'])/HZ/dt*100,2)))
            row['top_threads']=sorted(threads,key=lambda t:t['cpu_percent'],reverse=True)[:8]
        if row['cpu_one_core_percent']>=.2 or s['label'] in ('Isaac Kit','RViz2','ROS bag recorder') or row['rss_mib']>512:
            rows.append(row)
    delta=[a-b for a,b in zip(now_host['cpu'],before_host['cpu'])];total=sum(delta)
    report['samples'].append(dict(utc=datetime.now(timezone.utc).isoformat(),interval_s=dt,gpu=gpu(),
        host_cpu_busy_percent=round((1-(delta[3]+delta[4])/total)*100,2) if total else None,
        host_iowait_percent=round(delta[4]/total*100,2) if total else None,
        processes=sorted(rows,key=lambda r:r['cpu_one_core_percent'],reverse=True)[:24]))
    before,before_time,before_host=now,now_time,now_host
report.update(end_utc=datetime.now(timezone.utc).isoformat(),cgroup_end=cgroup(),host_end=host(),
              gpu_processes_end=gpu_processes(),storage_end=storage())
print(json.dumps(report))
