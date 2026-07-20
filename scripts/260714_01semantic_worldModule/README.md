# 260714_01semantic_worldModule

Standalone Isaac Sim project for fixed-step excavator motion and synchronized semantic-camera
capture. Version 2 keeps one RenderProduct alive for the full run, freezes Timeline state during
RT subframe rendering, and uses an authoritative frame context shared by the scheduler and Writer.

## Module boundaries

- `simulation_orchestrator.py`: SimulationApp lifecycle and top-level scheduling.
- `world_scheduler.py`: fixed-step Timeline/physics and future world properties.
- `excavator_joint_motion.py`: CSV trajectory loading, validation, interpolation, and Drive targets.
- `semantic_capture_custom.py`: Camera, RenderProduct, Writer, and capture calls only.
- `semantic_dataset_writer.py`: RGB and stable semantic dataset output.
- `semantic_mapping.py`: runtime-ID to dataset-ID mapping.
- `capture_context.py`: immutable frame identity, frozen-world snapshot, and Writer receipt.
- `capture_timing.py`: pure fixed-step frame/time mapping.
- `render_profile.py`: versioned render settings, application, and effective-value read-back.
- `stage_preflight.py`: read-only Stage, asset, Camera, semantics, and physics checks.
- `compare_render_quality.py`: matched-frame RGB quality metrics for GUI/script A/B tests.

The project is self-contained and does not import another local project.

## Default remote run

```bash
./run_capture_remote.sh \
  --renderer RealTimePathTracing \
  --frames 50 \
  --physics-hz 60 \
  --capture-fps 10 \
  --trajectory trajectories/excavator_motion_01.csv \
  --trajectory-mode loop \
  --interpolation linear \
  --width 1280 \
  --height 720 \
  --warmup-render-frames 16
```

`RealTimePathTracing` is the default renderer and resolves to RTX Real-Time 2.0, DLSS Quality,
and 16 RT subframes through `configs/render_realtime_pathtracing_720p.json`. The high-quality
alternative is selected with `--renderer PathTracing`; its default profile uses 8 samples per
pixel per render frame, 8 RT subframes, and a 64-SPP accumulation cap.

## Renderer selection

The two supported renderer choices are:

```bash
--renderer RealTimePathTracing
--renderer PathTracing
```

When `--render-profile` is omitted, the renderer selects one of these profiles:

```text
RealTimePathTracing -> configs/render_realtime_pathtracing_720p.json
PathTracing         -> configs/render_pathtracing_720p_64spp.json
```

An explicitly supplied profile must match an explicitly supplied renderer. A mismatch is an
error instead of silently overriding either input. A custom profile can be used on its own, in
which case its `renderer` field is authoritative. The schema-v1
`configs/render_quality_dlss_720p.json` profile is retained only for historical reproduction.

Path Tracing example:

```bash
./run_capture_remote.sh \
  --renderer PathTracing \
  --capture-mode static \
  --frames 3 \
  --width 1280 \
  --height 720 \
  --output /new/pathtracing/output
```

`--rt-subframes` and `--warmup-render-frames` override the selected profile's capture settings.
Path Tracing SPP, accumulation cap, denoiser, bounce limits, and reset policy remain profile-owned
so incompatible command-line combinations cannot be assembled accidentally. After every Stage
open, the program reapplies the selected SimulationApp renderer, applies the profile's Carb
settings, and reads every required setting back. Requested and effective renderer values, the
sampling model, and any mismatches are written to `run_config.json`.

Frame 0000 is captured at dataset time 0 by default. Pass `--no-capture-initial-frame` only when
the legacy behavior (first frame after one capture interval) is intentional.

Stage preflight is strict by default. Missing dependencies, an invalid Camera, missing semantics,
and authored non-positive mass/inertia values block production capture. Use `--no-strict-stage`
only for an explicitly marked diagnostic run while repairing an existing Stage.

## Static GUI/script parity capture

Camera_03 is a diagnostic reference, not a replacement for the production cab Camera_01:

```bash
./run_capture_remote.sh \
  --usd /absolute/stage.usda \
  --mapping /absolute/semantic_mapping.json \
  --camera /root/Camera_03 \
  --no-require-camera-below-cab \
  --capture-mode static \
  --frames 3 \
  --output /new/diagnostic/output
```

Static mode does not advance dataset physics time between captures. It is intended for a matched
Camera/Stage/render-profile comparison with Synthetic Data Recorder.

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

For schema-v2 outputs, `--expected-frames` is optional and defaults to the value recorded in the
run manifest. Validation checks frame context, dataset/timeline time, Writer completion counts,
RGB/semantic resolution, semantic mapping, and the expected static or moving transform behavior.

Matched RGB frames can be compared separately:

```bash
python compare_render_quality.py \
  --reference /path/to/gui_rgb.png \
  --candidate /path/to/script_rgb.png \
  --roi 500,100,250,300 \
  --output-report /path/to/quality_report.json
```

The tool deliberately marks metadata comparability as unverified; Stage hash, Camera matrix,
intrinsics, and simulation state must be matched before interpreting its image metrics.

## Output manifest

`run_config.json` uses schema version 2 and transitions through `running`, `complete`, or `failed`.
It records source-file hashes, render profile, effective Carb settings, Stage preflight, timing,
Camera state, Writer completion statistics, and software information. A failed or incomplete
manifest must not be treated as a production dataset.
