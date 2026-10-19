#!/usr/bin/python3
"""PYTHONEXE wrapper: debugger lives only in this experiment directory."""
import os,sys,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
out=Path(sys.argv[sys.argv.index("--out")+1])
trace=out/"native_trace.jsonl"
env=os.environ.copy()
inferior_keys=["LD_LIBRARY_PATH","LD_PRELOAD","PYTHONPATH","PYTHONHOME"]
inferior={k:env.get(k) for k in inferior_keys}
for k in inferior_keys:env.pop(k,None)
dbg=root/"debug_tools/gdb_root"
env["LD_LIBRARY_PATH"]=str(dbg/"usr/lib/x86_64-linux-gnu")
env["PYTHONHOME"]="/usr"
env["CAUSAL_TRACE_OUTPUT"]=str(trace)
commands=["set pagination off","set confirm off","set debuginfod enabled off",
          "set print thread-events off","set startup-with-shell off","set disable-randomization off",
          "set auto-load safe-path /","handle SIGPIPE nostop noprint pass"]
for k,v in inferior.items():
    commands.append("unset environment "+k if v is None else "set environment "+k+" "+v)
commands+=["source "+str(root/"trace_hook.py"),"run","quit"]
cmdfile=out/"debug_commands.gdb";cmdfile.write_text("\n".join(commands)+"\n")
args=[str(dbg/"usr/bin/gdb"),"-q","--batch","--data-directory="+str(dbg/"usr/share/gdb"),
      "-x",str(cmdfile),"--args","/root/isaacsim/kit/python/bin/python3",*sys.argv[1:]]
with (out/"debugger.log").open("x") as log:
    cp=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT)
sys.exit(cp.returncode)

