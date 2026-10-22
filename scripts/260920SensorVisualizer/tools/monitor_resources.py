"""One-second Linux sampler, standard library only; exits with its owner."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import time


def process(pid):
    root=Path('/proc')/str(pid)
    raw=(root/'stat').read_text();parts=raw[raw.rfind(')')+2:].split()
    status={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in (root/'status').read_text().splitlines()}
    data={line.split(':')[0]:int(line.split(':')[1]) for line in (root/'io').read_text().splitlines()}
    return dict(pid=pid,start_ticks=int(parts[19]),cpu_ticks=int(parts[11])+int(parts[12]),
        rss_kib=int(status['VmRSS'].split()[0]),threads=int(status['Threads']),
        read_bytes=data['read_bytes'],write_bytes=data['write_bytes'])


def sample_gpu():
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw',
            '--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=2)
        if result.returncode:return {'error':result.stderr[:200]}
        return [dict(zip(('index','utilization_percent','memory_used_mib','memory_total_mib','power_w'),row))
                for row in csv.reader(io.StringIO(result.stdout),skipinitialspace=True)]
    except (OSError,subprocess.TimeoutExpired) as exc:return {'error':str(exc)}


def main(pid,directory):
    previous={};hz=os.sysconf('SC_CLK_TCK');start_identity=process(pid)['start_ticks']
    with (directory/'resources.jsonl').open('a',encoding='utf-8') as out:
        while not (directory/'stop').exists():
            began=time.monotonic()
            try:
                if process(pid)['start_ticks']!=start_identity:break
            except (OSError,KeyError):break
            try:state=json.loads((directory/'runtime_status.json').read_text())
            except (OSError,ValueError):state={'tracked_pids':{'isaac':pid}}
            rows={}
            for role,child in state['tracked_pids'].items():
                try:
                    row=process(child);prior=previous.get(role)
                    if prior and prior['pid']==child and prior['start_ticks']==row['start_ticks']:
                        dt=began-prior['sample_time']
                        row.update(cpu_cores=(row['cpu_ticks']-prior['cpu_ticks'])/hz/dt,
                            read_bytes_per_s=(row['read_bytes']-prior['read_bytes'])/dt,
                            write_bytes_per_s=(row['write_bytes']-prior['write_bytes'])/dt)
                    previous[role]=dict(row,sample_time=began);rows[role]=row
                except (OSError,KeyError):pass
            cgroup={}
            for name in ('cpu.max','cpu.stat','memory.current','memory.max','memory.events','io.pressure'):
                try:cgroup[name]=(Path('/sys/fs/cgroup')/name).read_text().strip()
                except OSError:pass
            row=dict(unix_time_s=time.time(),monotonic_s=began,phase=state.get('phase'),
                simulation_time=state.get('simulation_time'),
                kit_heartbeat_age_s=began-state.get('last_update_monotonic_s',began),
                processes=rows,gpu=sample_gpu(),cgroup=cgroup,
                gpu_scope='whole device; not per sensor or process attribution')
            out.write(json.dumps(row)+'\n');out.flush()
            time.sleep(max(0.,1-(time.monotonic()-began)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--directory',type=Path,required=True);args=parser.parse_args()
    main(args.pid,args.directory)
