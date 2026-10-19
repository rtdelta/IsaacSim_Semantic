"""Run actual ROS2 closed-MCAP validation without editing published READY files."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from single0601_continuous_rt.validation import validate_recording


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    if a.directory.resolve() in a.report.resolve().parents:
        p.error('External report is required to preserve published evidence')
    if not (a.directory/'READY').exists():
        p.error('Read-only command requires a published READY dataset; failed-prefix validation is a separate diagnostic')
    report,_=validate_recording(a.directory)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sync_ok':report['sync_ok'],'completeness_ok':report['completeness_ok'],
                     'groups_verified':report['counts']['groups_verified'],'report':str(a.report)}))
    sys.exit(0 if report['sync_ok'] and report['completeness_ok'] else 2)
