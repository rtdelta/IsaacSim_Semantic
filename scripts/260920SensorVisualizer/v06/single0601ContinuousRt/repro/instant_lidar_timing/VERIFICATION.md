# Validation record — 2026-10-16

The four commands documented in README were executed with 20 targets each,
using the default headless mode and the scripts supplied in this package.

- Isaac Sim: `6.0.1-rc.7+release.42383.32955d8d.gl`.
- Kit: `110.1.2+production.326809.f9bf0dda.gl`.
- GPU/driver: NVIDIA L40 / 580.126.09.
- Separate Kit process per condition; four runs, 80 target scans, 104 native events.
- All four process exit codes: 0. All four measurement/cleanup checks: passed.
- Each frame retained all ten expected emitter identities. No intersection-only
  pairing, missing-frame substitution, geometry-based filtering, or pose fitting.
- Static controls matched current-pose geometry at approximately 2.53 µm.
- Rotation/BVH on matched the midpoint hypothesis in 20/20 targets.
- Rotation/BVH off matched the previous-step hypothesis in 20/20 targets.
- Both rotating controls matched current-pose geometry in 0/20 targets at the
  diagnostic 10 µm tolerance. This result is not itself an SDK-contract verdict.
- All 104 native payloads were saved, hashed and read back through the installed
  official parser during analysis. The point-cloud extractor agreed with that parser.
- Six local analytic checks covered axis-aligned wall hits, an oblique hit and a
  rotated hit with independently specified expected distances.
- No Kit process remained at suite completion.

Each reduced condition has one independent initialization. Repetition across
SDK builds, GPUs and GUI/headless modes has not been established. The original
larger experiment had additional repetitions and conditions; those are separate
evidence and are not counted as repeats of this reduced configuration.

One earlier development attempt stopped before target capture because creating
the stage reset DLSS execMode from 2 to 0. The initialization order was corrected
and all four controls were rerun into a new directory. The failed attempt is
retained in the private project records, not counted as geometric evidence.

The package includes no project credentials, remote-operation helpers, original
scene assets or full machine-specific runtime logs. Recorded sample metadata is
from the reduced simulation itself. Consult `manifest.json` for exact included
file hashes. `verified_results/*/source_hashes.json` links the run to the four
executable/configuration files in this directory.

The evidence supports a specific timing-semantics question. It does not establish
an internal SDK bug, a universal half-step interpolation rule, or successful
formal continuous-capture acceptance.
