# 260714_01semantic_worldModule

Standalone Isaac Sim project for fixed-step excavator motion and synchronized semantic-camera
capture. Version 3 drives the fixed-base four-DOF excavator through Isaac's Articulation position
API, reads the accepted joint state back after every physics step, and preserves the version-2
render/capture synchronization model.

## Module boundaries

- `simulation_orchestrator.py`: SimulationApp lifecycle and top-level scheduling.
- `capture_launch_config.py`: strict, versioned loading of every run-time business parameter.
- `world_scheduler.py`: fixed-step Timeline/physics and future world properties.
- `joint_control_profile.py`: self-contained four-joint and Recorder-sidecar contract.
- `articulation_stage_validator.py`: read-only fixed-base Articulation/rigid-link checks.
- `articulation_adapter.py`: named DOF binding and batched degree/radian conversion.
- `excavator_joint_motion.py`: CSV interpolation plus pre-step command/post-step readback.
- `semantic_capture_custom.py`: Camera, RenderProduct, Writer, and capture calls only.
- `semantic_dataset_writer.py`: RGB and stable semantic dataset output.
- `semantic_mapping.py`: runtime-ID to dataset-ID mapping.
- `capture_context.py`: immutable frame identity, frozen-world snapshot, and Writer receipt.
- `capture_timing.py`: pure fixed-step frame/time mapping.
- `render_profile.py`: versioned render settings, application, and effective-value read-back.
- `stage_preflight.py`: read-only Stage, asset, Camera, semantics, and physics checks.
- `compare_render_quality.py`: matched-frame RGB quality metrics for GUI/script A/B tests.

The project is self-contained and does not import another local project.

## Remote run

```bash
./run_capture_remote.sh \
  --config configs/capture_motion_camera02.json
```

`--config` is the only accepted business option. The JSON file contains the Stage, semantic
mapping, Camera Prim path, output, timing, motion, renderer, and strictness settings. Legacy
command-line options and extra Kit options are rejected instead of overriding the file.

The checked-in sample `configs/capture_motion_camera02.json` uses `RealTimePathTracing`, RTX
Real-Time 2.0, DLSS Quality, and the capture settings from
`configs/render_realtime_pathtracing_720p.json`.

Paths inside the launch configuration are resolved relative to the launch configuration's own
directory. This makes the sample's `usd`, `mapping`, `render_profile`, and `joint_profile` values
refer to neighboring files, while `../trajectories/...` and `../output/...` refer to project
directories.

## Renderer selection

The launch configuration must explicitly select one of the two supported renderer/profile pairs:

```text
RealTimePathTracing -> configs/render_realtime_pathtracing_720p.json
PathTracing         -> configs/render_pathtracing_720p_64spp.json
```

The configured profile must match the configured renderer. A mismatch is an error instead of
silently overriding either input. The schema-v1
`configs/render_quality_dlss_720p.json` profile is retained only for historical reproduction.

Set `rt_subframes` and `warmup_render_frames` in the launch JSON to override the selected
profile's capture settings. Set either value to `null` to retain the profile value.
Path Tracing SPP, accumulation cap, denoiser, bounce limits, and reset policy remain profile-owned
so incompatible combinations cannot be assembled accidentally. After every Stage
open, the program reapplies the selected SimulationApp renderer, applies the profile's Carb
settings, and reads every required setting back. Requested and effective renderer values, the
sampling model, and any mismatches are written to `run_config.json`.

Set `capture_initial_frame` to `true` to capture frame 0000 at dataset time 0. Set it to `false`
only when the legacy behavior (first frame after one capture interval) is intentional.

Stage preflight is strict by default. Missing dependencies, an invalid Camera, missing semantics,
and authored non-positive mass/inertia values block production capture. Motion mode additionally
requires one fixed-base Articulation root, exactly four named revolute DOFs in chain order, enabled
non-kinematic rigid links, finite limits, positive mass/inertia, and no Angular Drive API on the
controlled joints. Articulation failures always block motion capture; the `strict_stage`
configuration field only relaxes the general Stage diagnostics.

## Camera selection and static GUI/script parity capture

Every launch configuration must select one existing `UsdGeom.Camera` with `camera_prim_path`. The Camera can be
located anywhere in the Stage hierarchy; its parent controls inherited motion but does not affect
capture eligibility. The project does not discover a Camera automatically or require it to be
below the excavator cab.

```json
{
  "camera_prim_path": "/root/Camera_03",
  "capture_mode": "static",
  "enable_motion": false
}
```

Static mode does not advance dataset physics time between captures. It is intended for a matched
Camera/Stage/render-profile comparison with Synthetic Data Recorder.

The default Stage is `configs/Sim_Fangshan_07_capture_overlay.usda`. It sublayers
`/root/gpufree-data/wyb/StageMaterial02/Sim_Fangshan_07.usda`, whose fixed-base Articulation was
prepared for direct four-joint control. The matching native mapping is
`configs/semantic_mapping_Sim_Fangshan_07_native.json`. Older Sim_Fangshan_02 overlays and
mappings remain available for explicit static diagnostics and historical reproduction.

On the remote asset snapshot inspected on 2026-07-20, the source Stage references
`StageMaterial02/textures/color_121212.hdr`, but that file is absent. Missing image/environment-map
dependencies are recorded as `RENDER_ASSET_UNRESOLVED` warnings and no longer block strict capture.
Missing USD composition layers and unknown dependency types remain blocking errors. Camera,
semantics, and all Articulation contract failures also remain blocking.

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
targets are linearly interpolated at every physics step. `hold` is the default because trajectories
recorded by `260720_01JointPositionRecorder` are normally not closed. `loop` is accepted only when
the final four angles equal the initial angles.

If `<trajectory-stem>.metadata.json` exists, it is treated as a Recorder sidecar and must report a
completed degree-valued recording with exact joint order `cab,boom,small_arm,bucket`, compatible
direct-position control mode, and the matching excavator profile. A malformed or incompatible
sidecar is never ignored; hand-authored CSV files without a sidecar remain supported.

The Articulation wrapper and name-to-index mapping are created before Timeline playback. After
Timeline starts, bootstrap physics steps wait for the tensor entity, followed by one counted setup
step at trajectory time zero. Every subsequent physics step performs one batched four-DOF command
before stepping, zeros the selected DOF velocities, and reads all four positions after stepping.
The command, actual readback, and signed error are saved per frame. A readback error over the
profile tolerance (0.05 degree by default) stops the run instead of publishing misaligned labels.

## Validation

```bash
/root/isaacsim/python.sh validate_semantic_output.py \
  --output /absolute/output/path \
  --mapping configs/semantic_mapping_usd_ply_combined_02.json \
  --expected-frames 50
```

For schema-v2 and later outputs, `--expected-frames` is optional and defaults to the value
recorded in the run manifest. Schema-v3 validation additionally requires a passing Articulation
preflight, a bound/ready named-DOF mapping, counted bootstrap/setup steps, exact four-joint state
keys, finite command/readback/error values, safe limits, and the configured readback tolerance.

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

`run_config.json` uses schema version 4 and transitions through `running`, `complete`, or `failed`.
It records the source launch-configuration path and hash, the fully resolved effective
configuration, source-file hashes, render profile, effective Carb settings, Stage and
Articulation preflight, joint profile, Recorder metadata, runtime DOF binding, timing, Camera
state, Writer completion statistics, and software information. A failed or incomplete manifest
must not be treated as a production dataset.
