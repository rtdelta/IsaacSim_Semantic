"""ROS-side full decode and cross-version comparison; no Isaac imports."""
import io,json,sys
from pathlib import Path
import numpy as np
from PIL import Image
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.validate_capture import validate

def read(session):
    r=rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=str(session/'bag_unified'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={t.name:get_message(t.type) for t in r.get_all_topics_and_types()}
    groups={};current=0
    while r.has_next():
        topic,data,stamp=r.read_next()
        if topic=='/sensor_visualizer/frame_index':
            m=deserialize_message(data,types[topic]);idx=json.loads(m.data)
            groups.setdefault(stamp,{})['index']=idx
        elif topic.endswith('/points') or topic.endswith('/compressed'):
            m=deserialize_message(data,types[topic])
            if topic.endswith('/points'):value=np.frombuffer(bytes(m.data),dtype='<f4').reshape(-1,3).copy()
            else:value=np.array(Image.open(io.BytesIO(bytes(m.data))).convert('RGB'))
            groups.setdefault(stamp,{})[topic]=value
    return groups

def compare(a,b):
    ga,gb=read(a),read(b);stamps=sorted(set(ga)&set(gb));result={'common_groups':len(stamps),'pointclouds':[],'images':[],'pose_checks':[]}
    for stamp in stamps:
        x,y=ga[stamp],gb[stamp];ix,iy=x['index'],y['index']
        pose_errors=[]
        for kind in ('cameras','lidars'):
            for sid in ix[kind]:
                pose_errors.append(float(np.max(np.abs(np.array(ix[kind][sid]['to_world'])-np.array(iy[kind][sid]['to_world'])))))
        result['pose_checks'].append({'stamp_ns':stamp,'max_abs_matrix_error':max(pose_errors),'same_group_id':ix['group_id']==iy['group_id']})
        for topic in sorted(set(x)&set(y)-{'index'}):
            xx,yy=x[topic],y[topic]
            if topic.endswith('/points'):
                row={'stamp_ns':stamp,'topic':topic,'old_points':len(xx),'new_points':len(yy),'same_shape':xx.shape==yy.shape}
                try:
                    from scipy.spatial import cKDTree
                    distances=[]
                    for src,dst in ((xx,yy),(yy,xx)):
                        if len(src) and len(dst):
                            sample=src[np.linspace(0,len(src)-1,min(len(src),10000),dtype=int)]
                            nearest=cKDTree(dst).query(sample,workers=1)[0]
                            distances.append({'sample_count':len(sample),'mean_m':float(np.mean(nearest)),
                                'p95_m':float(np.quantile(nearest,.95)),'p99_m':float(np.quantile(nearest,.99)),
                                'max_m':float(np.max(nearest))})
                    row['bidirectional_sampled_nearest']=distances
                except ImportError:row['nearest_comparison_unavailable']='scipy not installed; no dependencies installed for test'
                if xx.shape==yy.shape:
                    difference=np.linalg.norm(xx.astype(float)-yy.astype(float),axis=1)
                    row.update(mean_delta_m=float(np.mean(difference)) if len(difference) else 0,
                        max_delta_m=float(np.max(difference)) if len(difference) else 0,
                        identical=bool(np.array_equal(xx,yy)))
                result['pointclouds'].append(row)
            else:
                delta=xx.astype(float)-yy.astype(float);mse=float(np.mean(delta**2))
                result['images'].append({'stamp_ns':stamp,'topic':topic,'shape':list(yy.shape),
                    'mae_8bit':float(np.mean(np.abs(delta))),'psnr_db':float(10*np.log10(255**2/mse)) if mse else None})
    return result

if __name__=='__main__':
    paths=[Path(p) for p in sys.argv[1:-1]]
    report={'validation':{str(p):validate(p,True) for p in paths},
            'comparison':{str(p):compare(paths[0],p) for p in paths[1:]}}
    Path(sys.argv[-1]).write_text(json.dumps(report,indent=2))
    print(json.dumps({'validated':len(paths),'comparison_file':sys.argv[-1]}))
