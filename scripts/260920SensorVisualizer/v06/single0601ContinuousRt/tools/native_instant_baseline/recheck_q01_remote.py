"""Read the retained failed-decoder packet set with corrected span validation."""
import os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');env=os.environ.copy()
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[k]='1'
program='''
import gzip,json,sys
from pathlib import Path
import numpy as np
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from tools.native_instant_baseline.io import rows,verify,save
from tools.native_instant_baseline.math_independent import decode
parent=root/'reports/native_instant_baseline/native005_20261015_v1/M_E/S0/r01/q01';c=parent/'continuous';files=verify(c);raw=rows(c/'raw_events.jsonl');errors=[];count=0
for r in raw:
    try:
        b=gzip.decompress((c/r['native_event']['packet_path']).read_bytes());h,a,xyz=decode(b);ex=np.frombuffer((c/r['payload_path']).read_bytes(),dtype='<f4').reshape(r['shape'])
        if not np.array_equal(xyz[(a['flags']&64)!=0],ex):raise ValueError('XYZ mismatch')
        count+=1
    except Exception as exc:errors.append({'receipt_seq':r['receipt_seq'],'error':str(exc)})
report={'scope':'Supplemental corrected ABI readback; original q01 FAILED measurement report remains unchanged and excluded from primary matrix','verified_files':files,'full_GMO_decoded':count,'raw_events':len(raw),'errors':errors}
save(parent/'corrected_decoder_readback.json',report);print(json.dumps(report))
'''
subprocess.run(['/usr/bin/python3','-B','-c',program,str(root)],env=env,check=True,timeout=90)
