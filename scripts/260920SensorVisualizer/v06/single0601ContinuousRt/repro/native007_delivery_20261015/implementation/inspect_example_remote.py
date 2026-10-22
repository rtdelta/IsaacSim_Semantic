import json,hashlib
from pathlib import Path
p=Path('/root/gpufree-data/Example_Rotary_90deg.usda')
print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'lines':p.read_text().splitlines()}))
