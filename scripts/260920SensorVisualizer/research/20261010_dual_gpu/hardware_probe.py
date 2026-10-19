"""Read hardware and resource constraints; do not start or alter project services."""
import concurrent.futures,hashlib,json,os,shutil,subprocess,time
from pathlib import Path

def read(path,limit=12000):
    try:return Path(path).read_text()[:limit].strip()
    except (OSError,UnicodeError):return None
def run(command,timeout=20):
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
        return {'exit_code':p.returncode,'stdout':p.stdout[:20000],'stderr':p.stderr[-2000:]}
    except Exception as exc:return {'error':type(exc).__name__+': '+str(exc)}
cmds={
 'lscpu':['lscpu','-J'],
 'gpu_inventory':['nvidia-smi','--query-gpu=index,uuid,name,pci.bus_id,driver_version,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,power.limit','--format=csv,noheader'],
 'gpu_topology':['nvidia-smi','topo','-m'],
 'gpu_p2p_read':['nvidia-smi','topo','-p2p','r'],
 'gpu_p2p_write':['nvidia-smi','topo','-p2p','w'],
 'gpu_pcie':['nvidia-smi','-q','-d','PCI'],
 'gpu_processes':['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader'],
 'gpu_graphics_processes':['nvidia-smi','pmon','-c','1','-s','um','-d','1'],
 'filesystem':['findmnt','-T','/root/gpufree-data','-n','-o','TARGET,SOURCE,FSTYPE,OPTIONS'],
 'profiler':['/opt/nvidia/nsight-systems/2025.1.1/bin/nsys','--version'],
}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=dict(zip(cmds,pool.map(run,cmds.values())))
cgroup={}
for prefix in ('/sys/fs/cgroup','/sys/fs/cgroup/cpu','/sys/fs/cgroup/cpuset','/sys/fs/cgroup/memory'):
    for name in ('cpu.max','cpu.stat','cpuset.cpus.effective','cpuset.mems.effective','memory.max','memory.current','memory.events','cpu.cfs_quota_us','cpu.cfs_period_us','memory.limit_in_bytes'):
        value=read(prefix+'/'+name)
        if value is not None:cgroup[prefix+'/'+name]=value
processes=[]
for proc in Path('/proc').glob('[0-9]*'):
    try:
        argv=(proc/'cmdline').read_bytes().split(b'\0')
        text=' '.join(x.decode(errors='replace') for x in argv)
        if any(s in text for s in ('260920SensorVisualizer','/root/isaacsim/kit/kit','/root/isaacsim/isaac-sim','rviz2','nsys profile')):
            processes.append({'pid':int(proc.name),'exe':os.readlink(proc/'exe'),
                'args':text[:1200],'status':read(proc/'status',3000)})
    except (OSError,ProcessLookupError):pass
samples=[]
for _ in range(5):
    samples.append({'monotonic_ns':time.monotonic_ns(),'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                    'gpu':run(cmds['gpu_inventory']),'cpu_stat':read('/proc/stat',3500),
                    'pressure':{name:read('/proc/pressure/'+name) for name in ('cpu','memory','io')}})
    if len(samples)<5:time.sleep(1)
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
manifest=json.loads((root/'deployment_manifest.json').read_text())
code_diff=[name for name,h in manifest.items() if not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest()!=h]
report={'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'identity':{
    'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()},
    'commands':results,'cpu_affinity':sorted(os.sched_getaffinity(0)),'cgroup':cgroup,
    'meminfo':read('/proc/meminfo',6000),'proc_cgroup':read('/proc/self/cgroup'),
    'loadavg':read('/proc/loadavg'),'numa_nodes':read('/sys/devices/system/node/online'),
    'disk':dict(zip(('total','used','free'),shutil.disk_usage('/root/gpufree-data'))),
    'isaac_version':read('/root/isaacsim/VERSION'),
    'tools':{s:shutil.which(s) for s in ('nsys','taskset','numactl','pidstat','iostat','vulkaninfo','nvcc')},
    'relevant_processes':processes,'samples':samples,
    'v06_code_manifest_files':len(manifest),'v06_code_diff':code_diff}
print(json.dumps(report))
