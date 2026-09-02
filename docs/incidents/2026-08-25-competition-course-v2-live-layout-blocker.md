# Competition Course V2 live layout blocker

Date: 2026-08-25
Status: RESOLVED 2026-09-01 — historical incident; infrastructure baseline unaffected

Resolution: the V2 course was rebased onto the accepted arena/spawn substrate,
gained deterministic geometry/transform validation and a top-down preview, and
was live-revalidated no-arm. The live run also exposed and fixed Class `1000813`
native-height scale calibration. Final 42/42 entity metadata, RGB/LiDAR/IMU,
Faster-LIO and obstacle evidence are recorded in
[`2026-09-01-competition-course-v2-map-acceptance.md`](../evidence/2026-09-01-competition-course-v2-map-acceptance.md).

## Scope

This incident records the first no-arm live inspection of the local
`feature/competition-map-v2` prototype. It does not reopen the accepted TF,
RViz, startup, lifecycle, or PBL-1 infrastructure baseline.

Prototype tip inspected:

```text
faa3901ae2bb868dfe0721c70c6fb38f70c46a3b
fix: gate competition course motion readiness
```

Live stack:

```text
stack-20260825T125357Z-6cf606d1
```

The run was intentionally no-arm. EGO-Swarm was not started after the course
layout was judged unsuitable for planner smoke.

## What was observed

The V2 source, generator, loader, deterministic motion controller, and dual
sensor path ran far enough to collect bounded evidence:

- the stack reached its current READY gate;
- both vehicles spawned and remained unarmed in `MANUAL`;
- both RGB streams produced non-empty RflySim scene images at about 18 Hz;
- both adapted LiDAR streams produced data at about 10 Hz;
- both IMU streams produced data at about 148–154 Hz;
- both Faster-LIO odometry and registered-cloud streams produced data at about
  10 Hz without an immediate fatal error;
- the configured moving entity produced a rolling pose trace with changing
  position.

These facts prove transport and entity activity only. They do **not** prove
that the competition course geometry is correct or traversable.

The camera evidence exposed a layout/spawn/view inconsistency:

- UAV1's forward view was dominated by a wall at very short range, with the
  scene opening to one side rather than presenting a clear start/queue area;
- UAV2's forward view terminated at a close wall/corner and did not resemble
  the intended shared course entry;
- the two vehicles, despite the specified parallel start poses, did not see
  mutually consistent views of the intended start area;
- neither landing ArUco marker was visible in the captured UAV RGB frames;
- the run did not establish that the static obstacle or moving obstacle was
  geometrically visible to LiDAR from the intended route.

Therefore `COURSE_READY` in this prototype only meant that entities and the
motion controller were created. It must not be interpreted as map geometry or
competition-course acceptance.

## Diagnosis boundary

The current evidence supports a problem in the map layer, most likely one or
more of:

1. ENU map specification to RflySim/UE entity-coordinate conversion;
2. wall center/extent/orientation generation;
3. CopterSim spawn position/yaw mapping relative to the generated entry;
4. camera pose/view assumptions used to validate the layout.

The evidence is not sufficient to select one mathematical correction yet.
No TF, Faster-LIO, MAVROS, EGO, mission, or vehicle-control change is justified
from this run.

## Acceptance impact

```text
Competition Course V2: BLOCKED
EGO smoke on V2: NOT RUN
V2 mission: NOT RUN
ArUco RGB visibility: NOT VERIFIED
Static/moving obstacle LiDAR visibility: NOT VERIFIED
Old predicted_narrow_course baseline: NOT MODIFIED
Infrastructure baseline f23de934: UNAFFECTED
```

The local prototype must not be called `COMPETITION MAP V2 READY` and must not
replace `predicted_narrow_course` as the default map.

## Required next investigation

Before another full live stack is started:

1. render a top-down, dimensioned 2D preview directly from the single-source
   map spec;
2. overlay UAV spawn position, yaw, camera forward axis, free-space envelope,
   corridor centerline, wall polygons, obstacle footprints, and landing pads;
3. unit-test every ENU-to-RflySim/UE position, rotation, and scale conversion
   against known SDK examples from the existing map pipeline;
4. verify that both spawn footprints have clearance and line of sight into the
   same intended queue/entry area;
5. add structural checks for wall overlap, accidental closure, route-envelope
   obstruction, and camera-facing assumptions;
6. run a map-only visual inspection before starting sensors, Faster-LIO, or
   EGO;
7. only after the map-only inspection passes, repeat bounded no-arm RGB/LiDAR
   evidence and then consider EGO smoke.

Do not compensate for this map problem by changing TF, planner parameters,
mission waypoints, takeoff height, or the protected infrastructure startup
sequence.
