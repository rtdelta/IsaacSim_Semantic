"""Create a credential-reference profile; identity pending until authentication."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
profile=json.loads(Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/config.json').read_text())
observed=json.loads((root/'new_host_observation.json').read_text())
profile['targets']['isaac-dual']={
    'host':observed['host'],'port':observed['port'],'username':'root',
    'auth':'windows-credential','credential_ref':'CloudInstanceOps/isaac-dual/ssh',
    'host_fingerprint':observed['host_fingerprint'],'hostname':'IDENTITY_PENDING',
    'machine_id_sha256':'0'*64,'workspace':'/root/gpufree-data',
    'identity_recorded':'PENDING: enrollment only; remote operations prohibited until identity recorded'}
(root/'targets.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
print(json.dumps({'profile':str(root/'targets.json'),'identity_pending':True}))
