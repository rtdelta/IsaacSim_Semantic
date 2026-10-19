"""Capture only the RViz X11 window using existing xwd and Pillow."""
import argparse, json, os, re, struct, subprocess
from pathlib import Path
import numpy as np
from PIL import Image

def main(destination,display=':20'):
    dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['DISPLAY']=display
    tree=subprocess.run(['xwininfo','-root','-tree'],env=env,capture_output=True,text=True,timeout=10)
    matches=[line for line in tree.stdout.splitlines() if 'RViz' in line and re.search(r'0x[0-9a-f]+',line)]
    if not matches:raise RuntimeError('No RViz window on the existing desktop')
    window=re.search(r'0x[0-9a-f]+',matches[0]).group()
    xwd=dest.with_suffix('.xwd')
    # Include composited OpenGL/Qt children, still bounded to this window.
    subprocess.run(['xwd','-screen','-id',window,'-out',str(xwd)],env=env,check=True,timeout=10)
    data=xwd.read_bytes();header=struct.unpack('>25I',data[:100])
    size,version,fmt,depth,width,height,offset,order,unit,bit_order,pad,bpp,stride,visual,red,green,blue,rgb_bits,entries,ncolors,*rest=header
    if version!=7 or fmt!=2 or bpp not in (24,32):raise ValueError('Unsupported XWD format')
    offset=size+ncolors*12
    if bpp==32:
        pixels=np.ndarray((height,width),dtype='<u4' if order==0 else '>u4',buffer=data,offset=offset,strides=(stride,4))
        channels=[]
        for mask in (red,green,blue):
            shift=(mask&-mask).bit_length()-1
            channels.append((((pixels&mask)>>shift)*255/(mask>>shift)).astype('u1'))
        rgb=np.stack(channels,axis=2)
    else:
        value=np.ndarray((height,width,3),dtype='u1',buffer=data,offset=offset,strides=(stride,3,1))
        rgb=value[:,:,::-1] if order==0 else value
    method='xwd'
    if not np.any(rgb):method='xwd-black-unverified'
    Image.fromarray(rgb).save(dest)
    print(json.dumps({'screenshot':str(dest),'window':window,'width':width,'height':height,'method':method,'nonblack':bool(np.any(rgb))}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--display',default=':20');a=p.parse_args();main(a.destination,a.display)
