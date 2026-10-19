"""Resolve renderer device explicitly; no CUDA visibility remapping."""
import csv
import io
import subprocess

def resolve_gpu(value):
    p=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,name','--format=csv,noheader'],capture_output=True,text=True,check=True)
    rows=[{'index':int(x[0].strip()),'uuid':x[1].strip(),'name':x[2].strip()} for x in csv.reader(io.StringIO(p.stdout))]
    matches=[x for x in rows if str(value) in (str(x['index']),x['uuid'])]
    if len(matches)!=1:raise ValueError('GPU must be an available UUID or index')
    return matches[0]
