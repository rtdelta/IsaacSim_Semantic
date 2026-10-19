"""Hash source, documentation, raw materials and generated asset for mirroring QA."""
from contract_math import ROOT, sha256, write_json


def inventory():
    files={}
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if not p.is_file() or any(x in ('reports','__pycache__') for x in rel.parts):continue
        files[rel.as_posix()]={'size':p.stat().st_size,'sha256':sha256(p)}
    result={'file_count':len(files),'total_bytes':sum(v['size'] for v in files.values()),'files':files}
    write_json(ROOT/'reports/delivery_inventory.json',result)
    print('DELIVERY_INVENTORY',result['file_count'],result['total_bytes'])
    return result


if __name__=='__main__':inventory()
