"""Read only the source project's paths, disk and required runtime inventory."""
import json,os,shutil,subprocess
from pathlib import Path
root=Path('/root/gpufree-data')
def listing(path):
    if not path.exists():return []
    return [{'name':p.name,'directory':p.is_dir(),'symlink':p.is_symlink(),
             'link_target':os.readlink(p) if p.is_symlink() else None}
            for p in sorted(path.iterdir()) if p.name not in {'.ssh','.cache'}]
row={'root':str(root),'root_entries':listing(root),'semantic_entries':listing(root/'semantic'),
     'asset_entries':listing(root/'IsaacSim_Asset'),'project_entries':listing(root/'semantic/scripts'),
     'sensor_project':listing(root/'semantic/scripts/260920SensorVisualizer'),
     'disk':dict(zip(('total','used','free'),shutil.disk_usage(root))),
     'tools':{n:shutil.which(n) for n in ('rsync','tar','ssh','python3','nvidia-smi')}}
row['gpu']=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,name,memory.total','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
print(json.dumps(row))
