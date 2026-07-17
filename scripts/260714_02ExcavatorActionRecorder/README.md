# 260714_02ExcavatorActionRecorder

Isaac Sim GUI panel for manually controlling the excavator's four angular Drives,
recording their target positions to CSV, and replaying the same CSV later.

## Inputs

- `--csv-dir`: CSV output directory in recording mode, or input directory in playback mode.
- `--csv-name`: filename only; it must end in `.csv`.
- `--record` / `--no-record`: enable or disable CSV recording controls. Recording is disabled by default.
- `--playback-mode hold|loop`: hold the last target or loop the trajectory.
- `--usd`: stage opened by the standalone launcher.

Enabling recording does not immediately create a file. Press **Start recording** in the panel.
Existing CSV files are never overwritten. Active recordings use `<name>.partial.csv` and are
published to the requested filename only after validation.

## Standalone GUI launch

```bash
cd /root/gpufree-data/repositories/260714_02ExcavatorActionRecorder
/root/isaacsim/python.sh run_gui.py \
  --usd /root/gpufree-data/wyb/StageMaterial/usd_ply_combined_02.usda \
  --csv-dir /root/gpufree-data/repositories/260714_02ExcavatorActionRecorder/trajectories \
  --csv-name excavator_manual_01.csv \
  --record \
  --playback-mode hold
```

## Attach to an already-running Isaac Sim GUI

Run the following in Isaac Sim's Script Editor after the excavator stage is open:

```python
import sys
from pathlib import Path

project = "/root/gpufree-data/repositories/260714_02ExcavatorActionRecorder"
if project not in sys.path:
    sys.path.insert(0, project)

from excavator_gui_recorder import RecorderGuiConfig, show_recorder_window

show_recorder_window(
    RecorderGuiConfig(
        csv_directory=Path(project) / "trajectories",
        csv_filename="excavator_manual_01.csv",
        recording_enabled=True,
        playback_mode="hold",
    )
)
```

## CSV format

The output is directly compatible with the previous semantic-capture trajectory player:

```csv
time,cab,boom,small_arm,bucket
0.000000000,-2.400000000,-8.000000000,29.666664000,-8.833334000
0.016666667,-2.300000000,-7.900000000,29.500000000,-8.700000000
```

Times are relative physics time and strictly increasing. Angular Drive targets are degrees.
The default playback mode is `hold`; `loop` additionally requires identical first and last targets.

## Tests

Pure Python:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Isaac Sim integration (headless UI smoke test):

```bash
/root/isaacsim/python.sh tests/isaac_gui_smoke_test.py
```

