"""CPU-only derived phase and observer analyses after all three short pairs."""
import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
base=root/'reports/clock_state_consistency/clock_20261014_v1'
for condition in ('qualification_B','qualification_static'):
    r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/phase_analysis.py'),str(base/condition/'repeats/r01')],capture_output=True,text=True,check=True)
    print(r.stdout)
r=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/clock_state/compare_observer.py'),str(base/'qualification_A/repeats/r01'),
    str(base/'qualification_B/repeats/r01'),str(base/'qualification_observer_comparison.json')],capture_output=True,text=True,check=True)
print(r.stdout)
