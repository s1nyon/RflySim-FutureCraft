# Competition Course V2 Layout Recovery Design

Date: 2026-08-25
Status: APPROVED CONCEPT — implementation pending
Branch: `feature/competition-map-v2`
Base infrastructure: `f23de934205b6776ef0531d46c26444bf9f7f65e`

## 1. Problem statement

The first no-arm live inspection of the V2 prototype showed three independent
map-level defects:

1. V2 moved the takeoff area from the accepted ENU `x ~= 16 m` arena to
   `x = 2 m`, placing its course in the near-origin region occupied by the
   native 28com/RflySim `SLAMScene` geometry;
2. project course layers were not mutually exclusive, so the V2 entities could
   coexist with entities from the prior `predicted_narrow_course` layer;
3. the geometry validator proved only structural validity, not that a vehicle
   with a realistic footprint and conservative clearance could pass static and
   moving obstacles.

The accepted infrastructure, TF contract, localization, planner, mission, and
vehicle-control paths are outside this correction.

## 2. Base-scene decision

Competition Course V2 will continue to use `SLAMScene`, but it will not place
project geometry in the native scene's occupied near-origin region. It reuses
the accepted `predicted_narrow_course` arena coordinates, floor, boundaries,
ceiling, takeoff area, corridor centerline, and landing area as its spatial
substrate. V2 adds competition elements to that proven substrate.

The rendered course is a project-owned dynamic layer over `SLAMScene`:

```text
SLAMScene native world
    + accepted project arena at x ~= 13.5..39.3 m
    + exactly one active project course layer
        - predicted_narrow_course, or
        - competition_course_v2
```

The design does not create a new UE map, require UE Editor, guess a new free
coordinate region, or accept two visually overlapping courses.

## 3. Course-layer exclusivity

### 3.1 Ownership boundary

Only IDs declared by version-controlled project map specifications may be
destroyed during a course transition. Unknown RflySim entities and unrelated
vehicle IDs are never swept by name or guessed from the live scene.

Known project ranges are currently:

```text
predicted_narrow_course: 12000..12999
competition_course_v2:   15000..15999
```

The implementation will centralize the transition policy in a small
project-owned helper used by both explicit map entrypoints. The helper will:

1. validate that declared course ranges are disjoint;
2. clear the inactive known project course range before loading the selected
   course;
3. clear the selected course's range before recreating its deterministic
   entities;
4. record the selected course, cleared ranges, created IDs, spec hashes, and
   timestamp in a transition receipt;
5. fail closed if a course, range, or receipt does not match a tracked spec.

This is map-entity ownership, not OS process ownership. It does not alter the
live-stack manifest schema or lifecycle process model.

### 3.2 Default isolation

The default startup remains `predicted_narrow_course`. V2 remains opt-in. A
transition back to the old map must remove V2's declared entity range before
the old layer is loaded, so regression direction is symmetric.

## 4. Coordinate and visual contract

The single V2 spec remains ENU and is the source of truth. All generated UE
commands must be derived through tested conversion functions:

```text
position: ENU [x, y, z] -> RflySim PosE/NED [north, east, down]
yaw:      ENU yaw        -> RflySim yaw
size:     desired metres -> asset-native scale
```

The generator will produce a deterministic top-down SVG containing:

- course centerline and direction arrows;
- wall polygons and wall IDs;
- UAV spawn footprints, yaw arrows, and forward-camera axes;
- static obstacle footprints;
- the moving obstacle pivot and full swept envelope;
- task zone, exit zone, landing platforms, and ArUco footprints;
- dimension labels for corridor widths and every minimum passable gap;
- a legend distinguishing official constraints, predicted geometry, and
  configurable safety parameters.

The preview and generated UE command manifest must be derived from the same
normalized geometry model. The preview is evidence, not a second geometry
source.

### 4.1 Accepted spatial substrate

The following coordinates are inherited from the live-verified predicted
course instead of being redesigned:

```text
takeoff bounds: [13.5, 18.5, -2.5, 2.5]
uav1 spawn:     [16.0, -0.7, 0.0], ENU yaw 0 deg
uav2 spawn:     [16.0,  0.7, 0.0], ENU yaw 0 deg

section A: [18.5, 0.0] -> [23.0, 0.0], width 1.5 m
corner A:  radius 0.9 m, left
section B: [23.9, 0.9] -> [23.9, 4.0], width 1.4 m
corner B:  radius 0.9 m, right
section C: [24.8, 4.9] -> [29.3, 4.9], width 1.5 m

landing bounds: [29.3, 34.3, 2.9, 6.9]
platform 1:     [32.0, 3.9]
platform 2:     [32.0, 5.9]
```

The V2 spec also owns deterministic copies of the accepted arena floor,
boundary walls, and ceiling objects under the V2 ID range. Loading V2 after
the transition removes the predicted layer first, then recreates one complete
arena/course layer with V2 IDs.

## 5. Vehicle envelope and clearance policy

### 5.1 Declared envelope

The existing `0.45 m` horizontal vehicle diameter is a predicted/configurable
engineering value, not an official competition dimension. Before flight
acceptance it must be replaced or confirmed by a measured maximum propeller-tip
footprint for the simulated FS-310 model.

Until that measurement is available, V2 uses conservative configurable values:

```text
declared vehicle diameter: 0.45 m
lateral safety margin:     0.25 m per side
minimum passable gap:      1.00 m
```

The mathematical minimum from diameter plus margins is `0.95 m`; the contract
rounds this up to `1.00 m`. The official maximum corridor width remains
`1.50 m`, so safety is obtained by obstacle placement rather than widening the
course beyond the rule.

### 5.2 Static obstacles

For every static obstacle cross-section, the validator computes all candidate
free slots between the obstacle footprint and corridor walls. At least one
continuous slot must be at least `1.00 m` wide after wall thickness and object
extent are applied.

The validator rejects:

- a gap computed from object centers instead of outer extents;
- a path that satisfies only the bare vehicle diameter;
- an obstacle that blocks the centerline without a conservative bypass;
- clearance that exists at one point but disappears within the vehicle's
  swept footprint through a turn.

### 5.3 Turns

The centerline turn radius stays within the official `<=1.0 m` requirement.
The vehicle is modeled as a horizontal disk swept along the candidate path.
The inner and outer walls must both retain at least `0.25 m` radial clearance
from that swept disk. Polygon chord approximation error is included in the
clearance calculation.

## 6. Moving-obstacle contract

The pendulum is allowed to temporarily block the corridor; the map need not be
passable at every phase. It must, however, provide a deterministic safe passage
window rather than an extreme or physically impossible gap.

The validator samples one complete period at no less than the configured
controller update rate and computes, for every sample:

- the obstacle's collision footprint;
- left and right free gaps to the corridor walls;
- the larger passable gap;
- whether that gap is at least `1.00 m`.

Acceptance requires:

```text
maximum safe-side gap >= 1.00 m
continuous safe window >= 1.50 s
period > 0
motion remains inside the declared obstacle zone
```

The `1.50 s` window is a configurable development-map value. It creates room
for later wait-and-go planning without claiming that the current mission can
already coordinate the crossing.

The preview shows both extreme poses and the full swept envelope. Static
validation reports the safe-window start, end, duration, and side.

The first revised profile uses a `0.20 m` lateral obstacle width, `30 deg`
amplitude, and `6.0 s` period in Section C. Exact placement remains derived
from the accepted centerline and must pass the sampled clearance/window
validator; these numbers are not accepted merely because they appear in the
spec.

## 7. Spawn and entry acceptance

Both UAV spawn disks, enlarged by the `0.25 m` safety margin, must:

- lie inside the declared takeoff area;
- not overlap each other;
- not intersect any wall or obstacle;
- have a clear forward connection to the same queue/entry free-space region;
- have camera forward axes consistent with the intended entry direction.

The validator rejects a spawn that is structurally inside the takeoff bounds
but faces a close wall or a different enclosure.

## 8. Measurement contract

The map is a competition benchmark, not only a visual scene. Its spec and
generated artifacts provide the reference geometry needed by later evaluators.
They do not consume simulator truth in the flight-control path.

### 8.1 Evidence planes

```text
map spec / generated semantics
    geometry, zones, centerline, obstacle truth, marker truth

RflySim/CopterSim ground truth
    actual vehicle and moving-entity state, contact/collision evidence

ROS runtime evidence
    Faster-LIO, MAVROS state/odom, EGO commands, setpoints, mission events

RViz
    visualization only; never the metric source of record
```

The exact ground-truth transport/API must be audited before a competition
evaluator is implemented. Topic names or SDK fields are not guessed in this
map correction.

### 8.2 Generated semantic artifact

Generation emits `evaluation_reference.json`, derived from the normalized
geometry model and containing:

- spec hash and coordinate contract;
- takeoff zone and spawn truth;
- corridor entry and exit gates;
- Section A/B/C centerline parameterization and cumulative `course_s` ranges;
- wall and static-obstacle polygons;
- pendulum pivot, collision footprint, deterministic trajectory parameters,
  swept envelope, and statically predicted safe windows;
- target-slot truth records;
- landing-platform and ArUco polygons;
- declared vehicle envelope and clearance policy;
- metric definitions and the primary evidence plane for each metric.

This artifact supports later offline alignment and scoring without adding a
runtime shared TF. Per-UAV localization estimates may be aligned for analysis
using a run-scoped transform derived from known spawn or verified simulator
initial truth; that transform is an evaluation artifact and is not published
to ROS TF.

### 8.3 Metrics enabled by the map

The reference must be sufficient to compute later:

- takeoff and corridor-entry time;
- Section A/B/C completion and along-track `course_s`;
- cross-track error and minimum wall clearance;
- minimum static- and moving-obstacle clearance;
- duration and use of pendulum safe windows;
- minimum inter-UAV distance;
- collision count, OFFBOARD loss, timeout, and mission duration;
- target detection recall and target-position error;
- landing-platform selection and horizontal ArUco landing error;
- localization error/drift when simulator truth is available.

Existing `stage8_control_chain_recorder.py`, `stage8_flight_metrics.py`,
`score_summary.py`, and `stage7_run_artifacts.py` remain runtime evidence
building blocks. Building the full competition evaluator is a later task; V2
must provide its stable reference contract now so the map does not need to be
redesigned around each algorithm experiment.

## 9. Test and validation strategy

Implementation follows test-first development.

### Offline red/green tests

1. A synthetic prior predicted layer plus V2 load must initially reproduce
   overlapping course IDs; the transition helper then removes only the known
   inactive range.
2. Switching from V2 back to predicted must remove V2 IDs symmetrically.
3. An unknown ID must never be included in the destruction plan.
4. A `0.99 m` static passage must fail; a `1.00 m` passage must pass.
5. A pendulum with no continuous `1.50 s` safe window must fail.
6. A pendulum with a compliant opening must report the correct time window.
7. A spawn facing a wall must fail even when its point lies inside takeoff
   bounds.
8. Preview generation must be deterministic and contain the same normalized
   IDs and bounds as the UE command manifest.
9. `evaluation_reference.json` must contain all three section ranges, geometry
   polygons, dynamic truth, landing truth, metric definitions, and the exact
   V2 spec hash.
10. No metric may name RViz as its primary evidence source.

### Static acceptance

- focused course tests;
- deterministic generation twice with byte/hash comparison;
- dimensioned SVG manual review;
- repository validation and docs links;
- `git diff --check`.

### Live ladder

Only after offline acceptance:

1. start clean `SLAMScene` and load V2 entities only;
2. inspect the map visually before starting sensor bridges;
3. verify that no predicted-course entities coexist with V2;
4. start bounded no-arm RGB/LiDAR collection;
5. verify wall, static obstacle, and moving obstacle visibility;
6. start Faster-LIO smoke;
7. start EGO smoke only after the map and sensor evidence pass;
8. switch back to `predicted_narrow_course` and verify the old layer is clean
   and unaffected.

No arming or V2 mission is required for this layout recovery.

## 10. Non-goals

- no TF or localization-frame changes;
- no EGO/Faster-LIO/PX4/MAVROS tuning;
- no mission or waypoint changes;
- no shared competition world frame;
- no UE Editor or new static UE map asset;
- no claim that geometric clearance proves planner success;
- no change to the default protected old-map behavior.
- no full competition evaluator or ground-truth bridge in this correction.

## 11. Rollback

The correction remains isolated on `feature/competition-map-v2`. The accepted
infrastructure commit and remote infra branch remain untouched. If the revised
map fails static or map-only live review, the V2 opt-in entrypoint stays
blocked and `predicted_narrow_course` remains the default regression map.
