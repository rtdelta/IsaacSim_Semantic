"""Serial experiment suite; each case owns a new directory and exact command."""
import pathlib,json,subprocess,time,sys
root=pathlib.Path(__file__).resolve().parent
manifest=json.loads((root/sys.argv[1]).read_text())
log=root/(pathlib.Path(sys.argv[1]).stem+"_status.jsonl")
for case in manifest:
    args=[sys.executable,str(root/"runner.py"),case["name"],"--script",case["script"],"--intervene",str(case["intervene"]),*case["args"]]
    started=time.time()
    cp=subprocess.run(args,capture_output=True,text=True)
    row={"name":case["name"],"exit_code":cp.returncode,"started":started,"finished":time.time(),"stdout":cp.stdout,"stderr":cp.stderr}
    with log.open("a") as f:f.write(json.dumps(row)+"\n")
    print(json.dumps(row),flush=True)
