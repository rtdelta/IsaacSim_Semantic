from pathlib import Path
import json,io,base64
from PIL import Image,ImageDraw
base=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v04/experiments')
columns=[('final_single_dome_baseline_v03','v03'),('final_gated_v04','v04 gated'),('production_throughput_v04','v04 keepalive')]
w,h=240,135; canvas=Image.new('RGB',(3*w,4*(h+20)+28),'#eeeeee');d=ImageDraw.Draw(canvas)
for col,(suffix,label) in enumerate(columns):
 out=next(base.glob('*_'+suffix));session=Path(json.loads((out/'capture_result.json').read_text())['session'])
 d.text((col*w+5,5),label,fill='black')
 for row,sid in enumerate(('front','back','left','right')):
  p=session/'validation_images'/(sid+'.png')
  if not p.is_file():raise RuntimeError('Missing validation export '+str(p))
  tile=Image.open(p).convert('RGB').resize((w,h),Image.Resampling.LANCZOS)
  y=28+row*(h+20);canvas.paste(tile,(col*w,y));d.text((col*w+5,y+h+3),sid,fill='black')
buffer=io.BytesIO();canvas.save(buffer,format='JPEG',quality=70)
if len(buffer.getvalue())>100000:buffer=io.BytesIO();canvas.save(buffer,format='JPEG',quality=45)
(base/'final_images_comparison.jpg').write_bytes(buffer.getvalue())
print(json.dumps({'encoding':'jpeg-base64','bytes':len(buffer.getvalue()),'data':base64.b64encode(buffer.getvalue()).decode()}))
