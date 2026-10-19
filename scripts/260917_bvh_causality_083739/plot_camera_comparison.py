from pathlib import Path
import json
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
root=Path(__file__).resolve().parent
font=FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
names=["inspection_v3_camera_gaussian_off.png","inspection_v3_camera_gaussian_on.png"]
fig,axes=plt.subplots(1,2,figsize=(12.8,5.6),dpi=150)
for ax,name,label in zip(axes,names,["Motion BVH 关闭：Gaussian 可见","Motion BVH 开启：Gaussian 消失"]):
    ax.imshow(Image.open(root/name));ax.axis("off");ax.set_title(label,fontproperties=font,fontsize=15,pad=12)
fig.suptitle("独立相机对照：没有活动 LiDAR，场景与相机均静止",fontproperties=font,fontsize=17,y=.98)
fig.text(.5,.035,"Isaac Sim 6.0.1-rc.7 / Kit 110.1.2 · multi-tick = OFF · per-sensor TLAS = OFF",
         ha="center",fontsize=10,color="#555555")
fig.subplots_adjust(left=.02,right=.98,top=.89,bottom=.095,wspace=.03)
fig.savefig(root/"camera_only_comparison.png",facecolor="white")
fig.savefig(root/"camera_only_comparison.pdf",facecolor="white")
plt.close(fig)

