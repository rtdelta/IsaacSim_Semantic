from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
r=Path(__file__).resolve().parent
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10})
fig,axes=plt.subplots(2,3,figsize=(13,7),gridspec_kw={"height_ratios":[3,1.8]},layout="constrained")
for col,(code,title) in enumerate([("A","A  |  Global Motion OFF"),("B","B  |  Global Motion ON"),("C","C  |  Global ON + Gaussian local mode 0")]):
    ax=axes[0,col];ax.imshow(Image.open(r/f"preview_camera_{code}.png"));ax.axis("off");ax.set_title(title,fontweight="bold",fontsize=11)
    a=np.load(r/f"preview_lidar_{code}.npz");d=np.linalg.norm(a["xyz"],axis=1);v=((a["flags"]&64)!=0)&(d>0)&(d<8)
    xyz=a["xyz"][v];ax=axes[1,col]
    if len(xyz):ax.scatter(xyz[:,0],xyz[:,1],s=4,c=d[v],cmap="viridis",vmin=0,vmax=8,alpha=.8)
    ax.set(xlim=(0,8),ylim=(-2,2),xlabel="Sensor X (m)",ylabel="Sensor Y (m)",title=f"NZ3 near returns: {len(xyz)}")
    ax.grid(alpha=.2);ax.set_aspect("equal")
fig.suptitle("Static scene: Gaussian visibility and LiDAR returns restored by local build-mode intervention",fontsize=13,fontweight="bold")
fig.savefig(r/"static_comparison.png",dpi=170)

