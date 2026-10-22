"""Bounded metadata and asset-reference inventory; do not execute project code."""
import json,os,re,shutil,subprocess
from pathlib import Path
root=Path('/root/gpufree-data')
scopes=['IsaacSim_Asset','semantic/scripts/260920SensorVisualizer','semantic/Materials','semantic/projects','camera']
excluded={'.git','__pycache__','.venv','.venv-web','.cache','node_modules','output','incoming','deploy_history','reports','backups'}
result={};references=[];links=[]
for name in scopes:
    base=root/name;count=size=0;largest=[]
    if base.exists():
        for current,dirs,files in os.walk(base,followlinks=False):
            dirs[:]=[d for d in dirs if d not in excluded]
            for d in dirs:
                p=Path(current)/d
                if p.is_symlink():links.append({'path':str(p),'target':os.readlink(p),'directory':True})
            for n in files:
                p=Path(current)/n
                if p.is_symlink():links.append({'path':str(p),'target':os.readlink(p),'directory':False});continue
                st=p.stat();count+=1;size+=st.st_size;largest.append((st.st_size,str(p)))
                if p.suffix.lower() in {'.usda','.json','.py','.kit'} and st.st_size<4*1024*1024:
                    text=p.read_text(encoding='utf-8',errors='replace')
                    values=re.findall(r'@([^@\r\n]+)@',text) if p.suffix=='.usda' else []
                    values+=re.findall(r'["\'](/root/gpufree-data/[^"\'\r\n]+)["\']',text)
                    for value in sorted(set(values)):
                        if '://' in value:references.append({'owner':str(p),'reference':value,'external':True});continue
                        q=Path(value) if value.startswith('/') else p.parent/value
                        references.append({'owner':str(p),'reference':value,'resolved':str(q.resolve()),'exists':q.exists()})
    result[name]={'files':count,'bytes':size,'largest':sorted(largest,reverse=True)[:8]}
install=Path('/root/isaacsim')
runtime={'isaac_path':str(install),'isaac_exists':install.exists(),'kit':(install/'kit/kit').exists(),
         'version_files':{n:(install/n).read_text(errors='replace')[:200] for n in ('VERSION','version.txt') if (install/n).is_file()},
         'ros_jazzy':Path('/opt/ros/jazzy/setup.bash').is_file(),'python3':shutil.which('python3'),
         'ssh':shutil.which('ssh'),'tar':shutil.which('tar'),'rsync':shutil.which('rsync')}
outside=[]
for row in references:
    if row.get('external') or not any(row.get('resolved','').startswith(str(root/n)+'/') or row.get('resolved')==str(root/n) for n in scopes):outside.append(row)
main=root/'IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda'
main_refs=[x for x in references if x['owner']==str(main)]
print(json.dumps({'scopes':result,'links':links,'references_total':len(references),'outside_scope_references':outside[:100],
    'main_stage_references':main_refs,'runtime':runtime}))
