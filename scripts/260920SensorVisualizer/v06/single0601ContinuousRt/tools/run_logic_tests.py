"""Run real pure contract/fault tests and save their actual result and source inventory."""
from pathlib import Path
import sys
import time
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0601_continuous_rt.common import save_json,file_hash,utc
output=ROOT/'reports'
output.mkdir(exist_ok=True)
started=time.monotonic()
with (output/'logic_tests.txt').open('w',encoding='utf-8') as stream:
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
report={'schema_version':1,'finished_utc':utc(),'tests_run':result.testsRun,'passed':result.wasSuccessful(),
        'duration_wall_s':time.monotonic()-started,'failures':[str(t) for t,_ in result.failures],
        'errors':[str(t) for t,_ in result.errors],'source_files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':file_hash(p)} for p in (ROOT/'tests').glob('test_*.py')],
        'scope':'Pure actual Python contracts; no claim of SDK, ROS or native keyboard acceptance'}
save_json(output/'logic_tests.json',report)
print(report)
raise SystemExit(0 if result.wasSuccessful() else 2)
