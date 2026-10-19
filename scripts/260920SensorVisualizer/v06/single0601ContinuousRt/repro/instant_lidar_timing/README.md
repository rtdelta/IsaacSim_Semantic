# Instant RTX LiDAR timing: small reproducible example

This example asks how instantaneous native ranges should relate to the source
simulation time and the `GenericModelOutput` (GMO) reported poses during rotation.
The hypothesis that every range should use the source-step pose is **not yet an
SDK contract confirmed by NVIDIA**. A residual against that hypothesis alone does
not establish an SDK defect.

## What runs

- One synthetic `OmniLidar`, created in code with ten zero-elevation rays at
  azimuths 10, 25, 40, 70, 110, 155, 200, 245, 290, and 335 degrees.
- Six static cube walls; inner room bounds X = [-7, 10], Y = [-11, 8], Z = [-4, 6] meters.
- Sensor origin (0, 0, 0); rotation about +Z is written in `PHYSICS_PRE_STEP`.
  Actual world transforms are recorded in `PHYSICS_POST_STEP`.
- Physics/rendering 60 Hz; sensor tick/scan 10 Hz; Instant on; accumulation on;
  SENSOR/CARTESIAN/NONCOMPENSATED; Multi-Tick and per-sensor TLAS on; transform history 64.
- 24 static warmup updates, 20 predetermined target scans, 12 drain steps.
- Four same-event native annotators: point cloud, GMO, simulation time, reference time.
  The installed official GMO parser is used **after capture**, not a custom payload decoder.
- Every event and payload is kept. There is no geometry-based sample selection,
  estimated time shift, fitted yaw, ROS publisher, business pipeline, or external asset.

`sensor.json` is a **custom synthetic diagnostic configuration**, not an official
NVIDIA sensor asset. Non-pattern numeric settings derive from an earlier qualified
custom sensor. The original 85,632-ray pattern is reduced to ten rays, with new
model/vendor labels. This reduced case requires its own validation; results from
the original sensor are not automatically attributed to it.

## Run on Linux

Use an existing, complete Isaac Sim installation with locally available extensions.
This package does not install dependencies or fetch sensor assets. The extension
registry is disabled. The launcher requires Python 3 standard-library modules;
Isaac's bundled Python supplies NumPy and sensor APIs to the capture script.

From this directory, set the installation location and run each command in a
**fresh output directory**:

```bash
ISAAC_ROOT=/path/to/isaacsim
python3 launch.py --isaac-root "$ISAAC_ROOT" --out results/static_on  --yaw-rate 0 --motion-bvh on
python3 launch.py --isaac-root "$ISAAC_ROOT" --out results/rotate_on  --yaw-rate 6 --motion-bvh on
python3 launch.py --isaac-root "$ISAAC_ROOT" --out results/static_off --yaw-rate 0 --motion-bvh off
python3 launch.py --isaac-root "$ISAAC_ROOT" --out results/rotate_off --yaw-rate 6 --motion-bvh off
```

Run serially on an otherwise idle GPU. Each invocation launches and exits its own
Kit process, with a 600-second watchdog. Default is headless. `--gui` is optional
and requires an existing display; it is a different startup mode and must be
validated separately. `--targets` accepts 4–100 (default 20). `--yaw-rate 3` is
available for further investigation but is not part of the four default controls.
Missing extensions or incompatible APIs should be reported as execution failures,
not as reproduction of a geometric inconsistency.

## Read the result

First check `summary.json`: `capture_complete`, `cleanup_ok`, and
`measurement_qualified` must all be true. A zero process exit code means that
capture, clocks, configuration, and analysis qualified; it does **not** mean the
reported behavior is a confirmed bug or that product acceptance passed.

`samples.csv` contains each target scan's three radial-distance residuals.
`per_ray.csv` exposes the observed and predicted distance for every returned ray.
Predictions are fixed before examining geometry:

| Column | Predicted sensor orientation |
|---|---|
| current | Actual source-step yaw |
| half | Arithmetic midpoint of actual previous/current yaw, within this small Z rotation |
| previous | Actual previous physical-step yaw |

For one horizontal ray, world direction is `(cos(yaw - azimuth), sin(yaw - azimuth))`.
Its predicted range is the smaller positive intersection distance with the two
applicable X/Y room walls. This calculation is implemented in `analyze.py:wall_range`.
Output range is `sqrt(x*x + y*y + z*z)` in SENSOR Cartesian coordinates, before
any consumer-side world transform. P95 uses the nearest-rank definition; with ten
returns it equals the largest residual. The 10 µm comparison threshold is our
diagnostic tolerance, **not a published NVIDIA accuracy guarantee**.

`half`/`previous` are geometric hypotheses, not observations of SDK interpolation
weights or history slots. `frameStart`/`frameEnd` are output metadata, not direct
traces of the actual transforms used for ray intersection.
The GMO timestamp is retained separately; the script does not assume its clock
domain is identical to simulation time or substitute it for the source/reference
association.

Qualification requires all ten valid emitter IDs, a complete scan, unique native
frame/time identity, agreement between official parser XYZ and extractor XYZ,
source/reference times mapping to the same unique physics step within 2 ns, one
physics step per update, exact 10 Hz source cadence, and complete target coverage.
Static warmup must match nominal geometry within the diagnostic tolerance.
Failures stop the run; no partial subset becomes a successful result.

## Files

- `launch.py`: isolated Kit process and timeout; no project-specific imports.
- `capture.py`: scene, native collection, fixed motion and actual-state recording.
- `analyze.py`: installed parser and independent analytic wall-distance calculation.
- `sensor.json`: all authored sensor values; no asset references.
- `VERIFICATION.md`: exact environment and executed validation results.
- `DISCUSSION_DRAFT.md`: short, cautious English question for maintainers.

Each run records settings, effective sensor values, environment, input physics
states, native events, full gzip-compressed GMO payloads, source hashes and source
copies, process status, and a Kit log. The output scene is generated locally.
The packaged `verified_results/` contains selected verification outputs; runtime
logs and machine-specific launch paths are retained separately in the project.
