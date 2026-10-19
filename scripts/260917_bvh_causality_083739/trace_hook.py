"""Loaded by an isolated GDB. Observe a known function; do not change its behavior."""
import gdb,json,os
from pathlib import Path
out=Path(os.environ["CAUSAL_TRACE_OUTPUT"])
seen=set()
class GaussianBuildTrace(gdb.Breakpoint):
    def stop(self):
        try:
            regs={k:int(gdb.parse_and_eval("$"+k)) for k in ["rdi","rsi","edx","ecx","r8","rsp"]}
            key=(regs["rdi"],regs["ecx"],regs["r8"])
            if key not in seen:
                seen.add(key)
                row={"event":"gaussian_build_tlas","object":hex(regs["rdi"]),"mode":regs["ecx"],
                     "device":regs["edx"],"bool_arg":regs["r8"]&255,
                     "thread":str(gdb.selected_thread().ptid),"thread_name":gdb.selected_thread().name,
                     "backtrace":gdb.execute("bt 16",to_string=True)}
                with out.open("a") as f:f.write(json.dumps(row)+"\n")
            if len(seen)>=12:self.enabled=False
        except Exception as e:
            with out.open("a") as f:f.write(json.dumps({"trace_error":str(e)})+"\n")
        return False
def on_objfile(event):
    if not event.new_objfile.filename.endswith("/librtx.scenedb.plugin.so"):return
    pid=gdb.selected_inferior().pid
    mappings=Path(f"/proc/{pid}/maps").read_text().splitlines()
    parts=[line.split() for line in mappings if line.endswith("/librtx.scenedb.plugin.so")]
    base=min(int(x[0].split("-")[0],16)-int(x[2],16) for x in parts)
    with out.open("a") as f:f.write(json.dumps({"event":"scenedb_loaded","pid":pid,"path":event.new_objfile.filename,"base":hex(base),"entry_offset":"0x184990"})+"\n")
    GaussianBuildTrace("*"+hex(base+0x184990),internal=True)
gdb.events.new_objfile.connect(on_objfile)

