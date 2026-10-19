"""Verify replay FK against actual captured USD poses, no rendering required."""
import argparse, json, math
from pathlib import Path
import numpy as np
from rviz_viewer.model import pose_matrix,forward_kinematics

def verify(capture):
    capture=Path(capture);manifest=json.loads((capture/'viewer_assets/manifest.json').read_text())
    targets=[json.loads(x) for x in (capture.parent/'trajectory/states.jsonl').read_text().splitlines()]
    rows=[json.loads(x) for x in (capture/'body_poses.jsonl').read_text().splitlines()]
    errors={}
    for row in rows:
        state=targets[row['group_id']]
        # The swing is held at the captured initial native angle (zero in this scene).
        angles={j['name']:math.radians(state['joints_deg'].get(j['name'],0)) for j in manifest['joints']}
        expected=forward_kinematics(manifest,pose_matrix(state['position_world_m'],state['quaternion_xyzw']),angles)
        for name,actual in row['body_world_row'].items():
            errors[name]=max(errors.get(name,0),float(np.max(np.abs(expected[name]-np.asarray(actual).T))))
    result={'groups':len(rows),'body_matrix_max_abs_error':errors,'passed':bool(rows) and max(errors.values())<2e-5,'pose_source':'actual captured USD bodies vs FK reconstructed from same requested root/joints and USD anchors'}
    (capture/'viewer_model_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));return 0 if result['passed'] else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture');a=p.parse_args();raise SystemExit(verify(a.capture))
