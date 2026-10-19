"""Publish the validated standalone asset, checking every deployed byte."""
import argparse
import shutil
from pathlib import Path
from contract_math import ROOT, load_config, sha256, write_json
import json


def publish(destination):
    cfg=load_config();source=ROOT/'assets'/cfg['asset_name'];destination=Path(destination).resolve()
    for name in ['geometry_validation.json','isaac_validation.json']:
        report=json.loads((ROOT/'reports'/name).read_text())
        if not report.get('passed'):raise RuntimeError('Validation missing or failed: '+name)
        if report.get('asset_manifest_sha256')!=sha256(source/'manifest.json'):
            raise RuntimeError('Validation is stale for '+name)
    if destination.exists():
        marker=destination/'manifest.json'
        if not marker.is_file() or json.loads(marker.read_text()).get('version')!=cfg['version']:
            raise FileExistsError('Refusing to replace an unrecognized asset directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,destination,dirs_exist_ok=True)
    files=[]
    for f in sorted(source.rglob('*')):
        if not f.is_file():continue
        rel=f.relative_to(source);a=sha256(f);b=sha256(destination/rel)
        if a!=b:raise RuntimeError('Deployment checksum mismatch: '+str(rel))
        files.append({'path':rel.as_posix(),'sha256':a})
    from usd_environment import initialize
    initialize()
    from pxr import Usd
    stage=Usd.Stage.Open(str(destination/(cfg['asset_name']+'.usda')))
    gaussians=[p for p in stage.Traverse() if p.GetTypeName()=='ParticleField3DGaussianSplat']
    assert len(gaussians)==5
    count=sum(len(p.GetAttribute('positions').Get()) for p in gaussians)
    assert count==sum(p['count'] for p in cfg['parts'])
    for layer in stage.GetUsedLayers():
        if not layer.anonymous:assert Path(layer.realPath).resolve().is_relative_to(destination)
    write_json(ROOT/'reports/deployment.json',{'passed':True,'destination':str(destination),'files':files,
        'relocated_stage_loaded':True,'gaussian_prims':len(gaussians),'total_gaussians':count})
    print('DEPLOYED',destination)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--destination',type=Path,default=Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Excavator_3DGS_Contract'))
    publish(p.parse_args().destination)
