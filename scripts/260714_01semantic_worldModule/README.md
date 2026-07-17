# 260714_01semantic_worldModule

Standalone Isaac Sim project for fixed-step excavator motion and semantic-camera capture.

## Module boundaries

- `simulation_orchestrator.py`: SimulationApp lifecycle and top-level scheduling.
- `world_scheduler.py`: fixed-step Timeline/physics and future world properties.
- `excavator_joint_motion.py`: CSV trajectory loading, validation, interpolation, and Drive targets.
- `semantic_capture_custom.py`: Camera, RenderProduct, Writer, and capture calls only.
- `semantic_dataset_writer.py`: RGB and stable semantic dataset output.
- `semantic_mapping.py`: runtime-ID to dataset-ID mapping.

The project is self-contained and does not import another local project.

## Default remote run

```bash
./run_capture_remote.sh \
  --frames 50 \
  --physics-hz 60 \
  --capture-fps 10 \
  --trajectory trajectories/excavator_motion_01.csv \
  --trajectory-mode loop \
  --interpolation linear \
  --width 1280 \
  --height 720 \
  --rt-subframes 4
```

The default Stage is `configs/usd_ply_combined_02_capture_overlay.usda`. It sublayers
`/root/gpufree-data/wyb/StageMaterial/usd_ply_combined_02.usda`, normalizes six semantic
classes, and disables nested child-mesh rigid bodies while retaining the parent rigid bodies
used by the four joints.

## Trajectory file

The default motion is stored in `trajectories/excavator_motion_01.csv`:

```csv
time,cab,boom,small_arm,bucket
0.0,-2.4,-8.0,29.666664,-8.833334
1.25,17.6,7.0,9.666664,16.166666
2.5,-2.4,-8.0,29.666664,-8.833334
3.75,-22.4,-23.0,49.666664,-33.833334
5.0,-2.4,-8.0,29.666664,-8.833334
```

The CSV is loaded once during initialization. Times must start at zero and increase strictly.
All joint targets are checked against the USD limits plus a two-degree safety margin. Runtime
targets are linearly interpolated at every physics step. `loop` requires the final joint targets
to equal the first targets; `hold` keeps the final keyframe after the trajectory duration.

## Validation

```bash
/root/isaacsim/python.sh validate_semantic_output.py \
  --output /absolute/output/path \
  --mapping configs/semantic_mapping_usd_ply_combined_02.json \
  --expected-frames 50
```
