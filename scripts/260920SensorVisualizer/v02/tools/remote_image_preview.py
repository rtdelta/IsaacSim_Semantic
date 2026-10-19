"""Return bounded JPEG previews of project-generated validation images only."""
import os
os.execv('/usr/bin/python3',['/usr/bin/python3','-c',r'''
from pathlib import Path
from PIL import Image,ImageDraw
import base64,io,json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02/reports/quality')
paths=sorted(root.glob('*.png'))
if not paths:
    output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v02')
    directories=sorted(output.glob('20*/validation_images'))
    paths=sorted(directories[-1].glob('*.png'))
paths=paths[:4]
sheet=Image.new('RGB',(1280,760),(20,20,20)); draw=ImageDraw.Draw(sheet)
crop=Image.new('RGB',(1280,700),(20,20,20)); cd=ImageDraw.Draw(crop)
for i,path in enumerate(paths):
    image=Image.open(path).convert('RGB'); x=(i%2)*640;y=(i//2)*380
    view=image.copy();view.thumbnail((640,350));sheet.paste(view,(x,y+25));draw.text((x+10,y+5),path.name)
    cx=(i%2)*640;cy=(i//2)*350
    region=image.crop((image.width//2-320,image.height//2-160,image.width//2+320,image.height//2+160))
    crop.paste(region,(cx,cy+25));cd.text((cx+10,cy+5),path.name+' center 1:1')
for quality in (80,65,50,35,20):
    items=[]
    for name,image in [('overview',sheet),('center_crops',crop)]:
        stream=io.BytesIO();image.save(stream,format='JPEG',quality=quality)
        items.append({'name':name,'jpeg_base64':base64.b64encode(stream.getvalue()).decode()})
    result=json.dumps({'source_files':[str(p) for p in paths],'previews':items})
    if len(result)<180000: break
assert len(result)<180000
print(result)
'''])
