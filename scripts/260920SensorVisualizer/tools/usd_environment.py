"""Locate installed Isaac USD and NVIDIA PLY converter; does not start Kit."""
import os
import sys
from pathlib import Path


def initialize():
    root=Path(os.environ.get('SV_ISAAC_ROOT','/root/isaacsim'))
    libs=sorted((root/'extscache').glob('omni.usd.libs-*'))
    converters=sorted((root/'extscache').glob('omni.kit.converter.gsplat-*'))
    if not libs or not converters:
        raise RuntimeError('Isaac USD / gsplat converter not found; set SV_ISAAC_ROOT')
    for p in [libs[-1],converters[-1]/'pip_prebundle']:
        sys.path.insert(0,str(p))
    return root,libs[-1],converters[-1]
