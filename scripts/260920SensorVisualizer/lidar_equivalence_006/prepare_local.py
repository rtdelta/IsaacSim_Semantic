"""Create independent reviewed source copies and observation-only instrumentation."""
import ast,hashlib,json,shutil,zipfile
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
files={}
for sub in ('frozen_runtime','lab'):
    for p in (B/'single06_lab'/sub).rglob('*'):
        if p.is_file() and p.suffix in ('.py','.json','.kit') and '__pycache__' not in p.parts:
            files['legacy/'+p.relative_to(B/'single06_lab').as_posix()]=p
files['legacy/kit_lab_entry.py']=B/'single06_lab/kit_lab_entry.py'
files['legacy/tools/validate_capture_data.py']=B/'single06_lab/tools/validate_capture_data.py'
for rel in ('run.py','kit_entry.py','experiment.py','continuous.py','motion.py','prepare.py','config/baseline.json','tools/validate_bag.py','tools/validate_groups.py'):
    files['native/'+rel]=B/'native_scene18_capture_005'/rel
(R/'backups').mkdir(exist_ok=True)
if (R/'backups/source_copies.zip').exists():raise RuntimeError('Already prepared; do not overwrite experiment')
with zipfile.ZipFile(R/'backups/source_copies.zip','x',zipfile.ZIP_DEFLATED) as z:
    for dest,src in files.items():
        p=R/dest;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,p);z.write(src,dest)
(R/'source_provenance.json').write_text(json.dumps({dest:{'source':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest()} for dest,src in files.items()},indent=2))
def edit(rel,old,new):
    p=R/rel;s=p.read_text(encoding='utf-8');assert s.count(old)==1,(rel,old,s.count(old));p.write_text(s.replace(old,new),encoding='utf-8')
edit('legacy/lab/runner.py',"job.update(groups=spec.get('groups',8),output_directory=str(directory/'captures'))", "job.update(groups=spec.get('groups',8),scene=spec['scene'],output_directory=str(directory/'captures'))\n    job['render']['background_dome']=None\n    job['render']['warmup_subframes']=16;job['render']['camera_subframes']=16;job['render']['capture_subframes']=2")
edit('legacy/kit_lab_entry.py',"    spec=json.loads(Path(os.environ['SL06_SPEC']).read_text())", "    spec=json.loads(Path(os.environ['SL06_SPEC']).read_text())\n    sys.path.insert(0,str(ROOT.parent))\n    from observations import install_legacy\n    install_legacy(Path(os.environ['SL06_SPEC']).parent)")
edit('native/experiment.py',"                xyz=np.ascontiguousarray(xyz,dtype='<f4').reshape(-1,3);rendered=np.asarray(cloud['info']['transform']).reshape(4,4)", "                xyz=np.ascontiguousarray(xyz,dtype='<f4').reshape(-1,3);rendered=np.asarray(cloud['info']['transform']).reshape(4,4)\n                from observations import save_cloud\n                save_cloud(out,index,sensors[i]['id'],xyz,stamp,rendered,cloud.get('info',{}))")
edit('native/experiment.py',"        actual_joints=art.get_dof_positions().numpy().copy()", "        actual_joints=art.get_dof_positions().numpy().copy()\n        from observations import save_state\n        save_state(out,index,stage,stamp)")
edit('native/kit_entry.py',"async def main():", "sys.path.insert(0,str(Path(__file__).resolve().parent.parent))\n\nasync def main():")
for p in R.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
print(json.dumps({'copied_files':len(files),'preserved_old_sources':True}))
