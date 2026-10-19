"""Bounded experiment runner. All writable runtime paths are new task-owned paths."""
import argparse,json,os,resource,signal,shutil,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("name");p.add_argument("--timeout",type=float,default=240)
p.add_argument("--script",default="probe_static_v2.py")
p.add_argument("--intervene",type=int,choices=[0,1],default=0)
a,rest=p.parse_known_args()
root=Path(__file__).resolve().parent
assert "/" not in a.name and a.name not in [".",".."]
out=root/"cases"/a.name;out.mkdir(parents=True,exist_ok=False)
worker=root/a.script
assert worker.resolve().parent==root
shutil.copyfile(worker,out/"probe_snapshot.py")
for name in ["trace_hook.py","debug_python.py","runner.py"]:
    shutil.copyfile(root/name,out/("snapshot_"+name))
env=os.environ.copy()
for k in ["PYTHONHOME","PYTHONPATH","LD_PRELOAD","VIRTUAL_ENV","CONDA_PREFIX"]:env.pop(k,None)
for k,sub in [("HOME","home"),("XDG_CACHE_HOME","cache"),("XDG_CONFIG_HOME","config"),
              ("XDG_DATA_HOME","data"),("XDG_STATE_HOME","state"),("TMPDIR","tmp"),
              ("CUDA_CACHE_PATH","cuda_cache"),("__GL_SHADER_DISK_CACHE_PATH","gl_cache")]:
    path=root/"runtime_seed"/sub;path.mkdir(parents=True,exist_ok=True);env[k]=str(path)
env["PYTHONDONTWRITEBYTECODE"]="1";env["ROS_DOMAIN_ID"]="173"
env["BVH_INTERVENTION"]=str(a.intervene)
env["PYTHONEXE"]=str(root/"debug_python.py")
install=Path("/root/isaacsim")
paths=[str(p) for pat in ["omni.sensors.nv.common-*/bin/checker_lib/bin","omni.sensors.nv.common-*/bin",
                        "omni.sensors.nv.lidar-*/bin/model_plugins"] for p in (install/"extscache").glob(pat)]
paths += [str(install/x) for x in ["kit/python/lib","kit","kit/kernel/plugins","kit/plugins/rtx"]]
env["LD_LIBRARY_PATH"]=":".join(paths)
_,hard=resource.getrlimit(resource.RLIMIT_NOFILE);resource.setrlimit(resource.RLIMIT_NOFILE,(min(65536,hard),hard))
command=[str(install/"python.sh"),str(worker),"--out",str(out),
         "--portable-root",str(root/"runtime_seed"/"portable"),*rest]
status={"command":command,"started_at":time.time()}
with (out/"console.log").open("x") as log:
    child=subprocess.Popen(command,cwd=install,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    status["pid"]=child.pid;(out/"process.json").write_text(json.dumps(status,indent=2))
    try:status["exit_code"]=child.wait(timeout=a.timeout);status["timed_out"]=False
    except subprocess.TimeoutExpired:
        status["timed_out"]=True;os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=8)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        status["exit_code"]=child.returncode
status["finished_at"]=time.time();status["duration"]=status["finished_at"]-status["started_at"]
(out/"process.json").write_text(json.dumps(status,indent=2))
print(json.dumps(status),flush=True)
