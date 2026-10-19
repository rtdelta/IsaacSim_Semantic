"""Kit --exec entry point to asynchronously open one explicitly supplied scene."""
import asyncio
import os
from pathlib import Path
import sys
import omni.usd

scene = os.environ.get('SV_COMBINE_SCENE') or next((str(Path(v)) for v in sys.argv[1:] if v.endswith('.usda') and Path(v).is_file()), None)
if scene is None or not Path(scene).is_file():
    raise ValueError('Set SV_COMBINE_SCENE or pass an existing combine scene USDA')
asyncio.ensure_future(omni.usd.get_context().open_stage_async(scene))
