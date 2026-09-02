# Competition Course V2 Map Baseline Closure Design

Date: 2026-09-01
Status: APPROVED BY EPIC REQUEST

## Scope

Close the map engineering loop left open by the 2026-08-25 live-layout incident.
The existing recovered `competition_course_v2.json` remains the only authored
geometry source. This closure must prove that the specification, generated
preview, RflySim entities, vehicle spawn/camera direction, and no-arm sensor
observations agree.

The work ends at map and sensor acceptance. It does not start EGO, OFFBOARD, a
mission, or any flight; it does not change lifecycle ownership, TF, PX4,
MAVROS, Faster-LIO parameters, EGO parameters, or mission behavior.

## Architecture

```text
config/maps/competition_course_v2.json
  -> pure geometry validation
  -> deterministic entity manifest + preview
  -> tested ENU-to-RflySim boundary
  -> receipt-owned RflySim loader
  -> map-only live inspection
  -> no-arm RGB/LiDAR/IMU/Faster-LIO evidence
```

The accepted `SLAMScene` arena and ENU coordinates from the layout-recovery
design are retained. The preview and loader continue to consume the normalized
model; no coordinates are copied into launch scripts or evidence tooling.

## Offline acceptance

The validator must fail closed on malformed numeric/schema data, discontinuous
course elements, invalid widths/radii, unsafe spawn envelopes/headings,
non-passable static obstacles, insufficient pendulum safe windows, invalid
landing geometry, and inconsistent generated entity geometry. Wall and route
checks may use deterministic conservative sampling rather than a general
computational-geometry dependency, but the approximation and sampling density
must be explicit in the report.

A dedicated transform contract covers origin, positive ENU X/Y, non-zero XYZ,
ENU yaw 0/+90/-90/180 degrees, wall centre/yaw, and non-unit object scale. The
loader boundary is exercised with the fake SDK so the test proves actual
`PosE`, `AngEuler`, and `Scale` arguments rather than duplicated formulas.

The generated top-down preview must show walls, centreline, both spawns,
heading/camera arrows, static obstacles, the pendulum sweep, landing pads and
markers, and key dimensions. SVG remains the deterministic primary preview;
it is directly inspectable and does not require another raster dependency.

## Live gates

Gate C1 starts the explicit V2 course using the existing manifest lifecycle and
keeps both vehicles unarmed. Evidence is limited to a small set of screenshots,
the exact load/transition receipts, motion trace, manifest identity, and scene
inspection notes. Any spec/preview/live disagreement returns to the cheapest
offline gate.

Gate C2 starts only the already-validated sensor and Faster-LIO stack, still
without EGO, OFFBOARD, or mission execution. Acceptance requires both UAVs to
produce RGB, LiDAR, IMU, and Faster-LIO output; saved observations must support
wall/obstacle visibility, moving-obstacle change, consistent forward views, and
designed landing-target accessibility. Topic activity alone is insufficient.

Lifecycle stop execution remains subject to the repository's explicit Red-Zone
authorization. Unknown/stale ownership or port/process conflicts fail closed.

## Completion rule

`MAP READY` is allowed only when all offline, C1, and C2 requirements have fresh
evidence. If the environment or safe lifecycle gate prevents either live level,
the truthful result is `BLOCKED`; offline success is not promoted to live map
acceptance.
