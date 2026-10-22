"""Verify the local delivered bag and record evidence without altering the files."""
import hashlib,json,os,sys,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DESTINATION=ROOT.parents[1]/'output/20261013_scene18_single06_300_mcap'
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit,verify_file
from cloud_ops.security import Redactor,private_directory

def main():
    source=json.loads((DESTINATION/'source_manifest.json').read_text(encoding='utf-8'))
    receipt_path=DESTINATION/'transfer_receipt.json';receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),Redactor(),'20261013-pull-single06-300','Verify each delivered MCAP segment and metadata against source observation','local-delivery-verification','local-files-only')
    results=[]
    try:
        earlier=verify_file(source['audit_log'])
        audit.event('transfer.audit.checked',result=earlier)
        for item in source['files']:
            path=DESTINATION/'bag_unified'/item['name'];assert path.resolve().is_relative_to(DESTINATION.resolve())
            h=hashlib.sha256()
            with path.open('rb') as f:
                while block:=f.read(4*1024**2):h.update(block)
            match=path.stat().st_size==item['bytes'] and h.hexdigest()==item['sha256']
            record={'name':item['name'],'bytes':path.stat().st_size,'sha256':h.hexdigest(),'matches_source':match}
            results.append(record);audit.event('artifact.local.verified',**record);assert match
        partials=list((DESTINATION/'bag_unified').glob('*.part'));assert not partials
        verification={'verified':True,'files':results,'verified_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'audit_log':str(audit.path),'original_transfer_audit':earlier,'scope':'All local bytes equal source hashes observed over identity-checked SSH. No claim about semantic accuracy or source security.'}
        if earlier['integrity']!='valid':verification['audit_limitation']='Original parallel transfer log has inconsistent sequence/hash chaining because worker events were not serialized; preserved unchanged. This independent serial verification audit records verified files. The helper now serializes worker audit events for future transfers.'
        (DESTINATION/'local_verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
        receipt['local_verification_audit']=str(audit.path);receipt['original_transfer_audit_integrity']=earlier['integrity'];receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        audit.finish('succeeded',files=len(results),bytes=sum(x['bytes'] for x in results));assert verify_file(audit.path)['integrity']=='valid'
        print(json.dumps({'verified':True,'files':len(results),'bytes':sum(x['bytes'] for x in results),'destination':str(DESTINATION),'verification_audit':str(audit.path),'original_transfer_audit_integrity':earlier['integrity']}))
    except BaseException as exc:
        if not audit.closed:audit.finish('failed',error_type=type(exc).__name__,error=str(exc))
        raise

if __name__=='__main__':main()
