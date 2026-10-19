import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer')
code="""import json,struct,numpy as np
from pathlib import Path
from PIL import Image
p=Path('/root/gpufree-data/semantic/scripts/261013Rviz2Viewer/reports/rviz_frame150.xwd');d=p.read_bytes();h=struct.unpack('>25I',d[:100]);offset=h[0]+h[19]*12
pixels=np.ndarray((h[5],h[4]),dtype='<u4' if h[7]==0 else '>u4',buffer=d,offset=offset,strides=(h[12],4))
png=np.asarray(Image.open(p.with_suffix('.png')))
print(json.dumps({'header':h,'bytes':len(d),'pixel_min':int(pixels.min()),'pixel_max':int(pixels.max()),'first_pixels':pixels[::100,::100].tolist(),'png_min':int(png.min()),'png_max':int(png.max())}))
"""
p=subprocess.run(['/usr/bin/python3','-c',code],capture_output=True,text=True,timeout=10)
print(p.stdout);print(p.stderr)
