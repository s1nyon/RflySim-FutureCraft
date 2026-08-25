# Competition Course V2 Layout Recovery Design

Date: 2026-08-25
Status: APPROVED CONCEPT — implementation pending
Branch: `feature/competition-map-v2`
Base infrastructure: `f23de934205b6776ef0531d46c26444bf9f7f65e`

## 1. Problem statement

The first no-arm live inspection of the V2 prototype showed two independent
map-level defects:

1. project course layers were not mutually exclusive, so the V2 entities could
   coexist with entities from the prior `predicted_narrow_course` layer;
2. the geometry validator proved only structural validity, not that a vehicle
   with a realistic footprint and conservative clearance could pass static and
   moving obstacles.

The accepted infrastructure, TF contract, localization, planner, mission, and
vehicle-control paths are outside this correction.

## 2. Base-scene decision

Competition Course V2 will continue to use the existing clean `SLAMScene`
base. It does not require the 28com_sim competition-course geometry.

The rendered course is a project-owned dynamic layer over `SLAMScene`:

```text
clean SLAMScene
    + exactly one active project course layer
        - predicted_narrow_course, or
        - competition_course_v2
```

The design does not create a new UE map, require UE Editor, offset V2 to a
distant coordinate region, or accept two visually overlapping courses.

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

## 7. Spawn and entry acceptance

Both UAV spawn disks, enlarged by the `0.25 m` safety margin, must:

- lie inside the declared takeoff area;
- not overlap each other;
- not intersect any wall or obstacle;
- have a clear forward connection to the same queue/entry free-space region;
- have camera forward axes consistent with the intended entry direction.

The validator rejects a spawn that is structurally inside the takeoff bounds
but faces a close wall or a different enclosure.

## 8. Test and validation strategy

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

## 9. Non-goals

- no TF or localization-frame changes;
- no EGO/Faster-LIO/PX4/MAVROS tuning;
- no mission or waypoint changes;
- no shared competition world frame;
- no UE Editor or new static UE map asset;
- no claim that geometric clearance proves planner success;
- no change to the default protected old-map behavior.

## 10. Rollback

The correction remains isolated on `feature/competition-map-v2`. The accepted
infrastructure commit and remote infra branch remain untouched. If the revised
map fails static or map-only live review, the V2 opt-in entrypoint stays
blocked and `predicted_narrow_course` remains the default regression map.
