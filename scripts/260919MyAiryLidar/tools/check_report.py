"""Propagate the validation result after Kit's fast shutdown."""
import argparse
import json
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args,_=parser.parse_known_args()
report=json.loads((args.output/'validation.json').read_text())
raise SystemExit(0 if report.get('passed') else 1)
