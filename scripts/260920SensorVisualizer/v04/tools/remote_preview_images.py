"""Produce a small review sheet from the test's decoded MCAP images."""
from pathlib import Path
import json,subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v04')
out=Path(json.loads((root/'reports/latest_test.json').read_text())['directory'])
session=json.loads((out/'acceptance.json').read_text())['captures'][0]['session']
source='''from pathlib import Path
from PIL import Image,ImageDraw
import base64,io,json,sys
path=Path(sys.argv[1])/'validation_images'
sheet=Image.new('RGB',(1024,552),(25,25,25));draw=ImageDraw.Draw(sheet)
for i,name in enumerate(('front','back','left','right')):
    im=Image.open(path/(name+'.png')).convert('RGB');im.thumbnail((512,256))
    x=(i%2)*512;y=(i//2)*276
    sheet.paste(im,(x+(512-im.width)//2,y+20));draw.text((x+8,y+5),name,fill='white')
b=io.BytesIO();sheet.save(b,format='JPEG',quality=85)
print(json.dumps({'base64':base64.b64encode(b.getvalue()).decode(),'source':str(path)}))
'''
result=subprocess.run(['/usr/bin/python3','-c',source,session],capture_output=True,text=True,timeout=20)
if result.returncode:raise RuntimeError(result.stderr)
print(result.stdout)
