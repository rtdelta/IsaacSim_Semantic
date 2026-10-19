import pathlib,time,subprocess,sys,json
root=pathlib.Path(__file__).resolve().parent
status=root/'static_repeat_status.jsonl'
for _ in range(900):
    if status.exists() and len(status.read_text().splitlines())>=8:
        results=[json.loads((root/'cases'/x['name']/'result.json').read_text()) for x in json.loads((root/'static_repeat.json').read_text())]
        if any(x['status']!='collected' for x in results):raise RuntimeError('Static repetition failed; inspect first')
        raise SystemExit(subprocess.call([sys.executable,str(root/'suite_v2.py'),'motion_first.json']))
    time.sleep(2)
raise RuntimeError('Static repetition did not finish')
