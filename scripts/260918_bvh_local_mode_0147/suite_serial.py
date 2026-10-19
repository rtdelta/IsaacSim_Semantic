"""Serial cold-start cases; resume by writing a new suite manifest."""
import pathlib,json,subprocess,time,sys
root=pathlib.Path(__file__).resolve().parent
manifest=json.loads((root/sys.argv[1]).read_text())
log=root/(pathlib.Path(sys.argv[1]).stem+"_status.jsonl")
for case in manifest:
    args=[sys.executable,str(root/"runner.py"),case["name"],"--intervene",str(case["intervene"]),"--geometry",case["geometry"],"--output",case["output"],"--bvh",str(case["bvh"]),"--warmup","60","--frames","120"]
    if case["output"]=="lidar":args+=["--native-nz3","--instant","1"]
    started=time.time()
    cp=subprocess.run(args,capture_output=True,text=True)
    row={"name":case["name"],"exit_code":cp.returncode,"started":started,"finished":time.time(),"stdout":cp.stdout,"stderr":cp.stderr}
    with log.open("a") as f:f.write(json.dumps(row)+"\n")
    print(json.dumps(row),flush=True)
