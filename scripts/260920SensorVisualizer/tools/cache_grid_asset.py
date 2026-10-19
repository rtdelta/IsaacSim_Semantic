"""Cache the unchanged NVIDIA grid and its three textures for offline composition."""
import json
from pathlib import Path
import shutil
import urllib.request
from contract_math import ROOT, sha256, write_json

BASE = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/Grid/'
FILES = ['default_environment.usd', 'Materials/Textures/Wireframe_blue.png',
         'Materials/Textures/WireframeBlur_basecolor.png', 'Materials/Textures/WireframeBlur_blue.png']


def main():
    cfg = json.loads((ROOT/'config/combine_stage.json').read_text())
    cache = ROOT/'assets/NvidiaGrid'; output = Path(cfg['grid_asset']).parent
    manifest = {'source_base_url': BASE, 'policy': 'Byte-for-byte cache; geometry, materials and textures unchanged', 'files': []}
    for rel in FILES:
        path = cache/rel; path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with urllib.request.urlopen(BASE+rel, timeout=30) as response:
                data = response.read()
            assert data, rel
            path.write_bytes(data)
        target = output/rel; target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists(): assert sha256(target) == sha256(path), f'Existing cache differs: {target}'
        else: shutil.copy2(path, target)
        manifest['files'].append({'path': rel, 'url': BASE+rel, 'bytes': path.stat().st_size, 'sha256': sha256(path)})
    write_json(cache/'source_manifest.json', manifest)
    write_json(output/'source_manifest.json', manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__': main()
