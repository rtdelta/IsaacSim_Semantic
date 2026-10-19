"""Generate a compact evidence figure from recorded measurements (no fitted offsets)."""
from pathlib import Path
import json,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from deskew import PoseHistory
p=Path(__file__).resolve().parent
m={x['case']:x for x in json.loads((p/'motion_analysis.json').read_text())}
g=json.loads((p/'geometry_analysis.json').read_text())['parts'][:5]
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(1,3,figsize=(16,4.7))
x=np.arange(5)
ax[0].bar(x-.18,[i['median_m']*1000 for i in g],.36,label='Median',color='#1c8b8b')
ax[0].bar(x+.18,[i['p95_m']*1000 for i in g],.36,label='P95',color='#afcfd1')
ax[0].set_xticks(x,['Track','Cab','Boom','Arm','Bucket'],rotation=25)
ax[0].set_ylabel('Center-to-mesh distance (mm)')
ax[0].set_title('A  Geometry correspondence');ax[0].legend(frameon=False)
names=['Translation\n60 Hz, 2 m/s','Translation\n120 Hz, 1 m/s','Translation + yaw\n1 m/s, 30 deg/s']
on=['fixed_sensor_physics_retry','fixed_sensor_physics_120','fixed_sensor_yaw_zero_damping']
off=['fixed_sensor_physics_off',None,'fixed_sensor_yaw_off_zero_damping']
x=np.arange(3)
ax[1].bar(x-.17,[m[n]['returned_points_at_ray_time']['p95_m']*1000 for n in on],.34,label='BVH on',color='#1c8b8b')
for i,n in enumerate(off):
 if n:ax[1].bar(i+.17,m[n]['returned_points_at_ray_time']['p95_m']*1000,.34,label='BVH off' if i==0 else None,color='#d77a52')
ax[1].set_xticks(x,names);ax[1].set_yscale('log');ax[1].set_ylim(.001,200)
ax[1].set_ylabel('P95 ray intersection error (mm, log)')
ax[1].set_title('B  Physics-clock motion truth');ax[1].legend(frameon=False)
n='fixed_sensor_physics_retry'
r=json.loads((p/'cases'/n/'result.json').read_text())
s=next(x for x in r['samples'] if x['cycle']==0 and x['timestampNs']==500000000)
d=np.load(p/'cases'/n/s['file']);u=[x for x in r['updates'] if x['cycle']==0]
h=PoseHistory([round(x['physics_time']*1e9) for x in u],[x['moving_position'] for x in u],[[0,0,0,1]]*len(u))
world=h.deskew(d['xyz'],s['timestampNs']+d['timeOffsetNs'].astype('int64'))
nr=json.loads((p/'cases/fixed_sensor_physics_world/result.json').read_text())
ns=next(x for x in nr['samples'] if x['cycle']==0 and x['timestampNs']==500000000)
nd=np.load(p/'cases/fixed_sensor_physics_world'/ns['file'])
ax[2].plot(nd['timeOffsetNs']*1e-6,nd['xyz'][:,0],color='#d77a52',label='Native WORLD, accumulated')
ax[2].plot(d['timeOffsetNs']*1e-6,world[:,0],color='#1c8b8b',label='Raw SENSOR + physics poses')
ax[2].axhline(10,color='black',ls=':',label='True wall x = 10 m')
ax[2].set_xlabel('Ray offset within scan (ms)');ax[2].set_ylabel('World x (m)')
ax[2].set_ylim(9.97,10.20);ax[2].set_title('C  World-coordinate reconstruction');ax[2].legend(frameon=False,fontsize=8,loc='center')
fig.suptitle('Isaac Sim 6.0.1-rc.7 / Kit 110.1.2 / L40 — isolated diagnostic evidence',fontsize=14)
fig.text(.015,.015,'A uses Gaussian centers with opacity >= 0.5; it is not a LiDAR depth-equivalence claim. B uses ideal noise-free planes and fixed beams.',fontsize=9)
fig.tight_layout(rect=[0,.055,1,.95])
fig.savefig(p/'motion_geometry_results.png',dpi=170)

