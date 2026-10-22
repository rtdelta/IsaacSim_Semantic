"""Structured per-card, cgroup and CPU/thread sampling without new packages."""
import csv
import io
import os
from pathlib import Path
import subprocess
import time

class ResourceDetails:
    def __init__(self,diag):
        self.diag=diag;self.previous={};self.cgroup_previous=None;self.io_previous={}

    def stat(self,path,key,now):
        fields=path.read_text().rsplit(')',1)[1].split()
        cpu=(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
        faults=(int(fields[7]),int(fields[9]))
        previous=self.previous.get(key);self.previous[key]=(now,cpu,*faults)
        return {'cpu_cores':(cpu-previous[1])/(now-previous[0]) if previous and now>previous[0] else None,
                'state':fields[0],'cpu_total_s':cpu,'minor_faults_total':faults[0],'major_faults_total':faults[1],
                'minor_faults_delta':faults[0]-previous[2] if previous else None,
                'major_faults_delta':faults[1]-previous[3] if previous else None}

    def sample(self,pids,smi):
        started=time.monotonic_ns();cpu_started=time.thread_time_ns();now=time.monotonic();alive_keys=set()
        result={'processes':{},'gpu_source':'nvidia-smi sampled whole-device busy time; not per-function latency or SM occupancy'}
        for role,pid in list(pids.items()):
            try:
                row=self.stat(Path(f'/proc/{pid}/stat'),(pid,'process'),now);alive_keys.add((pid,'process'))
                row['pid']=pid;status=Path(f'/proc/{pid}/status').read_text().splitlines()
                for field,target in (('VmRSS:','rss_bytes'),('VmSize:','virtual_bytes')):
                    row[target]=next(int(x.split()[1])*1024 for x in status if x.startswith(field))
                for field,target in (('voluntary_ctxt_switches:','voluntary_context_switches'),
                                     ('nonvoluntary_ctxt_switches:','involuntary_context_switches')):
                    row[target]=next((int(x.split()[1]) for x in status if x.startswith(field)),None)
                row['cpu_allowed_list']=next((x.split(':',1)[1].strip() for x in status if x.startswith('Cpus_allowed_list:')),None)
                try:
                    values={line.split(':')[0]:int(line.split(':')[1]) for line in Path(f'/proc/{pid}/io').read_text().splitlines()}
                    prior=self.io_previous.get(pid);self.io_previous[pid]=values
                    row['io_total']=values;row['io_delta']={key:value-prior.get(key,0) for key,value in values.items()} if prior else None
                except (OSError,ValueError):row['io_total']=None
                threads=[]
                for task in Path(f'/proc/{pid}/task').glob('[0-9]*'):
                    try:
                        key=(pid,int(task.name));thread=self.stat(task/'stat',key,now);alive_keys.add(key)
                        thread.update(tid=int(task.name),name=(task/'comm').read_text().strip()[:80]);threads.append(thread)
                    except (OSError,ValueError,IndexError):pass
                row['threads']=len(threads)
                row['top_threads']=sorted(threads,key=lambda t:t['cpu_cores'] or 0,reverse=True)[:self.diag.config.get('resource_thread_top_n',8)]
                row['main_thread']=next((t for t in threads if t['tid']==pid),None)
                result['processes'][role]=row
            except (OSError,ValueError,IndexError,StopIteration):pass
        self.previous={k:v for k,v in self.previous.items() if k in alive_keys}
        self.io_previous={pid:values for pid,values in self.io_previous.items() if (pid,'process') in alive_keys}
        root=Path('/sys/fs/cgroup')
        for name in ('cpu.max','cpuset.cpus.effective','cpuset.mems.effective','memory.current','memory.max','memory.events','cpu.pressure','memory.pressure','io.pressure'):
            try:result['cgroup_'+name]=(root/name).read_text().strip()
            except OSError:pass
        try:
            values={line.split()[0]:int(line.split()[1]) for line in (root/'cpu.stat').read_text().splitlines()}
            result['cgroup_cpu_stat']=values
            if self.cgroup_previous:
                result['cgroup_cpu_delta']={k:values[k]-self.cgroup_previous[1].get(k,0) for k in values}
                result['cgroup_interval_s']=now-self.cgroup_previous[0]
            self.cgroup_previous=(now,values)
        except (OSError,ValueError):pass
        try:result['load_average']=Path('/proc/loadavg').read_text().strip()
        except OSError:pass
        if smi:
            columns=['index','uuid','pci.bus_id','utilization.gpu','utilization.memory','memory.used','memory.total','power.draw','temperature.gpu']
            try:
                query=subprocess.run([smi,'--query-gpu='+','.join(columns),'--format=csv,noheader,nounits'],
                                     capture_output=True,text=True,timeout=2)
                result['gpus']=[dict(zip(columns,[v.strip() for v in row])) for row in csv.reader(io.StringIO(query.stdout))]
                result['gpu_query_returncode']=query.returncode
                compute=subprocess.run([smi,'--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'],
                                       capture_output=True,text=True,timeout=2)
                result['gpu_compute_processes']=[dict(zip(('pid','gpu_uuid','memory_mib'),[v.strip() for v in row]))
                                                 for row in csv.reader(io.StringIO(compute.stdout))]
                result['gpu_process_query_returncode']=compute.returncode
            except (OSError,subprocess.TimeoutExpired) as exc:result['gpu_error']=str(exc)
        result['sampler_wall_ns']=time.monotonic_ns()-started
        result['sampler_thread_cpu_ns']=time.thread_time_ns()-cpu_started
        return result
