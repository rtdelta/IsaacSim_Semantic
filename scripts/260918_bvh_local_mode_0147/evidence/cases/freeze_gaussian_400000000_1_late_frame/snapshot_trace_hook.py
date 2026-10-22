"""Diagnostic only: inspect resources and optionally change a Gaussian-local mode."""
import gdb,json,os,hashlib,struct,time
from pathlib import Path
out=Path(os.environ["CAUSAL_TRACE_OUTPUT"])
intervene=os.environ.get("BVH_INTERVENTION")=="1"
expected_sha="3fc6bb790d164decaf40aa52c5c76a6401e67e210f395e40cea9ea20ac6c57f0"
base=None
objects=set()
active={}
counts={"entries":0,"modified":0,"normal_call":0,"normal_return":0,"callback_return":0,"init_call":0,"init_return":0,"errors":0}
seen=set()
def emit(event,**kw):
    with out.open("a") as f:f.write(json.dumps({"event":event,"wall_time":time.time(),**kw})+"\n")
def reg(k):return int(gdb.parse_and_eval("$"+k))
def mem(p,n):return bytes(gdb.selected_inferior().read_memory(p,n))
def u64(p):return struct.unpack("<Q",mem(p,8))[0]
def u32(p):return struct.unpack("<I",mem(p,4))[0]
def threadkey():return str(gdb.selected_thread().ptid)
def slots(obj):
    return {name:hex(u64(obj+off)) for name,off in [("tlas0_device0",0xa00),("tlas1_device0",0xa80),("scratch0_device0",0xc00),("scratch1_device0",0xc80),("instances",0x978)]}
class Probe(gdb.Breakpoint):
    def __init__(self,offset,kind):
        self.kind=kind
        super().__init__("*"+hex(base+offset),internal=True)
    def stop(self):
        try:
            key=threadkey()
            if self.kind=="init_call":
                obj=reg("rbx");desc=reg("rsi")
                objects.add(obj);counts["init_call"]+=1
                active[(key,"init")]=obj
                emit("init_call",object=hex(obj),mode=u32(desc+0x48),descriptor_hex=mem(desc,80).hex(),tlas_array=hex(reg("rdx")),scratch_array=hex(reg("rcx")),gaussian_count=u64(obj+0x960))
            elif self.kind=="init_return":
                obj=active[(key,"init")];counts["init_return"]+=1
                emit("init_return",object=hex(obj),return_code=reg("eax"),slots=slots(obj))
            elif self.kind=="entry":
                obj=reg("rdi");mode=reg("ecx");flag=reg("r8")&255;device=reg("edx")
                caller=u64(reg("rsp"))-base
                if mode not in (0,1) or flag!=0 or device!=0 or caller!=0x1eba3e or obj not in objects:
                    raise RuntimeError("Unexpected Gaussian call: "+str((hex(obj),mode,flag,device,hex(caller),obj in objects)))
                counts["entries"]+=1
                effective=mode
                if intervene and mode==1:
                    gdb.execute("set $ecx = 0",to_string=True)
                    effective=reg("ecx")
                    if effective!=0:raise RuntimeError("Mode override did not take effect")
                    counts["modified"]+=1
                active[(key,"build")]={"object":hex(obj),"mode_original":mode,"mode_effective":effective,"device":device,"bool":flag,"call_index":counts["entries"]}
                row=active[(key,"build")].copy()
                row["slots"]=slots(obj)
                if (obj,mode) not in seen:
                    seen.add((obj,mode));row["backtrace"]=gdb.execute("bt 14",to_string=True)
                emit("build_entry",**row)
            elif self.kind=="normal_call":
                row=active[(key,"build")];counts["normal_call"]+=1
                target=u64(reg("rbx")+0x448)
                emit("normal_build_call",**row,command_target=hex(target),command_module=gdb.solib_name(target),descriptor_hex=mem(reg("rsi"),104).hex())
            elif self.kind=="normal_return":
                counts["normal_return"]+=1
                emit("normal_build_return",**active[(key,"build")])
            elif self.kind=="callback_return":
                counts["callback_return"]+=1
                emit("callback_return",**active[(key,"build")],task_mode=u32(reg("rbp")+0x8c))
        except Exception as exc:
            counts["errors"]+=1;emit("trace_error",kind=self.kind,error=str(exc),counts=counts)
            return True
        return False
def on_objfile(event):
    global base
    if not event.new_objfile.filename.endswith("/librtx.scenedb.plugin.so"):return
    path=Path(event.new_objfile.filename)
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected_sha:raise RuntimeError("Unexpected SceneDB binary SHA256: "+actual)
    pid=gdb.selected_inferior().pid
    maps=[line.split() for line in Path(f"/proc/{pid}/maps").read_text().splitlines() if line.endswith("/librtx.scenedb.plugin.so")]
    base=min(int(x[0].split("-")[0],16)-int(x[2],16) for x in maps)
    emit("scenedb_loaded",pid=pid,path=str(path),sha256=actual,base=hex(base),intervene=intervene)
    for offset,kind in [(0x183e68,"init_call"),(0x183e6d,"init_return"),(0x184990,"entry"),(0x184c46,"normal_call"),(0x184c4c,"normal_return"),(0x1eba3e,"callback_return")]:
        Probe(offset,kind)
def on_exit(event):
    emit("trace_summary",intervene=intervene,counts=counts,objects=[hex(x) for x in objects],exit_code=getattr(event,"exit_code",None))
gdb.events.new_objfile.connect(on_objfile)
gdb.events.exited.connect(on_exit)
