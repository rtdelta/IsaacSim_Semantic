# How should Instant RTX LiDAR ranges relate to source-time poses during continuous rotation?

Hello Isaac Sim team,

I would like to confirm the intended measurement-time semantics before treating
this observation as a bug. A small executable reproduction and measured outputs
are attached. AI assisted with preparing the scripts and analysis; the reduced
case was actually executed on the environment below.

**Environment:** Isaac Sim `6.0.1-rc.7+release.42383.32955d8d.gl`, Kit
`110.1.2+production.326809.f9bf0dda.gl`, Linux, NVIDIA L40, driver 580.126.09, headless.
No other SDK build or GPU has been tested for this reduced case.

**Setup:** one synthetic ten-ray OmniLidar at the origin in a static rectangular
room. Rays are horizontal, with zero configured angular noise and emitter fire
times. Physics/rendering are 60 Hz; sensor tick/scan are 10 Hz. Instant,
accumulation, Multi-Tick and per-sensor TLAS are enabled; output is
SENSOR/CARTESIAN/NONCOMPENSATED. The sensor rotates about +Z at 6 degrees/second.
The profile is custom, not a stock NVIDIA sensor asset.

We write the pose in PHYSICS_PRE_STEP and record its actual world transform in
PHYSICS_POST_STEP. Same-event simulation time and mapped ReferenceTime uniquely
identify the same physics step within 2 ns. We copy native GMO and point-cloud
data, then use the installed official GMO parser after capture. There is no ROS
publisher, consumer-side world transform, registration, or fitted time offset.

For each returned emitter, its nominal direction and the room planes give an
analytic range. We compare three fixed hypotheses: actual source-step yaw,
midpoint of the previous/current physical-step yaw, and previous-step yaw.
The source-step hypothesis is **an expectation we want to verify with you**,
not an SDK contract we claim has already been established.

Each control was run in a separate Kit process with 20 predetermined target
scans. All scans had one valid return for each of all ten emitters; clock,
configuration, input, parser/extractor agreement and coverage checks passed.

| Condition | Current pose | Midpoint pose | Previous pose |
|---|---:|---:|---:|
| Static, Motion BVH on | 0.00253 mm | 0.00253 mm | 0.00253 mm |
| 6°/s, Motion BVH on | 7.646 mm | 0.00249 mm | 7.647 mm |
| Static, Motion BVH off | 0.00253 mm | 0.00253 mm | 0.00253 mm |
| 6°/s, Motion BVH off | 15.292 mm | 7.645 mm | 0.00274 mm |

Values are the median across 20 scans of each scan's nearest-rank P95 absolute
range residual over ten rays (therefore the maximum over those ten rays).
The 10 µm matching threshold used by the diagnostic is not a claimed NVIDIA
accuracy specification. The hypotheses do not establish actual SDK history
indices or interpolation weights.

Questions:

1. In this Instant/NONCOMPENSATED configuration, which time and pose should the
   raw ranges correspond to? Is the observed midpoint behavior expected?
2. What are the intended relationships between the source simulation time,
   GMO timestamp, frameStart/frameEnd, and the pose actually used for ray queries?
3. Is the change when Motion BVH is disabled expected? If so, which supported
   configuration or output metadata allows unambiguous geometric reconstruction?

The attached `README.md` has four commands; no external sensor or scene asset is
needed. `verified_results/` includes the per-scan/per-ray tables and complete
native payloads from the reduced case. Full runtime logs can be supplied if
needed. We have not traced the internal consumed transforms, and are not claiming
a specific SDK function or interpolation defect.
