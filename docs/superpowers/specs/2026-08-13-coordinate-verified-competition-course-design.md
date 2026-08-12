# Coordinate-Verified Competition Course Design

## 1. Purpose

Replace the current predicted narrow course with a competition-oriented map
whose physical placement is machine-verifiable. The redesign may replace the
entire existing centreline, floor, walls, ceiling, obstacle layout, task zones,
and landing area. It retains the protected no-arm lifecycle, `SLAMScene` base
map, official RflySim model requirement, and project-owned dynamic-object
loading approach.

The primary acceptance question is no longer whether the scene looks correct.
It is whether commanded geometry and RflySim-reported world geometry agree
within declared tolerances. Human review remains authoritative only for visual
suitability such as logos, colors, textures, and competition semantics.

## 2. Requirements Basis

The predicted course covers the published competition requirements that are
stable enough to implement before the official map is released:

- at least three scored narrow-channel segments;
- channel width no greater than `1.5 m` in the competition profile;
- segment length at least `3 m` and turn radius no greater than `1 m`;
- a flat, obstacle-free takeoff area with at least two takeoff positions;
- static obstacles such as cones, posts, and supports;
- a swinging suspended dynamic obstacle;
- one instance of each unknown task class: colored label, QR code, and thermal
  anomaly proxy;
- at least two ArUco `4x4_250` landing platforms outside the channel, separated
  by at least `1.5 m`;
- reproducible randomized locations and marker IDs;
- no dependence on UE Editor or modification of installed RflySim assets.

The PDF contains both `0.5 m` and `0.6 m` landing-marker descriptions. The
default is `0.6 x 0.6 m`, with marker size exposed as a single profile parameter
so it can be changed to `0.5 x 0.5 m` without changing platform coordinates.

## 3. Coordinate and Geometry Authority

### 3.1 Frames

The course specification uses ENU coordinates in metres. It is the only design
truth. Conversion to the vendor NED command frame occurs only at the UE API
boundary. Yaw uses ENU radians in configuration and is converted at the same
boundary.

Every entity has:

- a stable project-owned object ID;
- an official ClassID and source reference;
- a pose in either course ENU or a declared channel-local frame;
- commanded scale and expected full dimensions;
- an explicit support relationship;
- expected static or dynamic behavior;
- acceptance tolerances and evidence state.

No loader may silently infer a frame or treat a model actor origin as its
geometric centre.

### 3.2 Channel-Local Coordinates

The centreline is a sequence of lines and circular arcs. A point attached to a
channel segment is represented by `(segment, s, n, h)`:

- `s`: distance along the segment centreline;
- `n`: signed horizontal normal offset, positive to the left of travel;
- `h`: height above the resolved support surface.

Changing channel width moves walls along the local normal. It does not change
the centreline, along-course locations, target allocation, takeoff zone, or
landing zone. Obstacles and task targets therefore remain semantically stable
between development and competition profiles.

### 3.3 World Bounds from Official Metadata

RflySim reports an actor position `p`, local box origin `o`, half extent `e`,
and attitude. The verifier transforms the eight corners of the local box by
the reported attitude and actor transform. It must not add or compare
`boxOrigin` as though it were already a world coordinate.

For an axis-aligned zero-roll/zero-pitch object, the vertical bounds reduce to:

```
world_bottom_z = actor_z + local_box_origin_z - half_extent_z
world_top_z    = actor_z + local_box_origin_z + half_extent_z
```

The general implementation uses transformed corners so future yaw, roll, or
pitch does not invalidate the calculation.

## 4. Selected Course Topology

The selected topology is the balanced Z-shaped course, option C from the design
comparison. It contains:

- a `6 x 5 m` obstacle-free takeoff zone;
- segment S1, approximately `7 m` long;
- a 90-degree turn with centreline radius `1.65 m`;
- segment S2, approximately `5 m` long;
- a second 90-degree turn with centreline radius `1.65 m`;
- segment S3, approximately `7 m` long;
- a landing zone outside the S3 exit;
- two fixed landing-platform centres separated by `1.8 m`.

Exact centreline endpoints, arc centres, wall polygons, and zone bounds are
derived in the implementation plan and stored as numeric configuration. Every
derived dimension must be included in the generated validation report.

The fixed centreline radius makes the inner radii `0.75 m` for the `1.8 m`
development profile and `0.90 m` for the `1.5 m` competition profile. Both are
non-degenerate and satisfy the published maximum inner-radius constraint.

The course has no arena-wide ceiling. A suspended obstacle may have a local
support frame, but its collision geometry and swept volume are explicit and
must not cover unrelated placement stations.

## 5. Width Profiles

One topology produces two width profiles:

| Profile | Clear channel width | Purpose |
| --- | ---: | --- |
| `development` | `1.8 m` | Incremental integration and diagnosis |
| `competition` | `1.5 m` | Published-rule acceptance and stress testing |

Both profiles use identical centreline and task semantics. A report must name
the active width profile and prove the minimum measured clear width after UE
loading. Passing the development profile never implies passing the competition
profile.

## 6. Explicit Support Surfaces

Automatic ground-fitting APIs are prohibited for coordinate-verified course
entities. The current live experiment showed why: the west ceiling covered the
showcase positions, and `sendUE4PosScale2Ground` attached models to the ceiling
instead of the floor.

Each placeable object names a support entity and support face. Common cases are:

- obstacles supported by the course floor top face;
- task targets supported by a side-wall face or edge-mounted support;
- ArUco images supported by a landing-platform top face;
- a suspended body supported by a local hanger pivot, not by the floor.

The loader first obtains the support object's actual world bounds from official
metadata. It computes the actor pose needed to align the child's designated box
face with the support face, sends a normal `sendUE4PosScale` command, then reads
the child metadata again. No successful receipt is produced until the measured
support gap is within tolerance.

The support graph must be acyclic. Missing metadata, an ambiguous support face,
or a support surface outside expected bounds fails closed before dependent
objects are placed.

## 7. Official Asset Policy

Only official RflySim models and documented official image mechanisms are used.
An asset is eligible only after metadata calibration and role-specific sensor
evidence; existence of a ClassID is not role approval.

ClassIDs `500`, `750`, and `1000` are excluded from the new course and showcase.
Their installed asset packages reference `Logo.uasset`, and the operator has
rejected the visible Feisi-branded appearance. Exclusion applies to generation,
loading, verification, random selection, and future role approval.

The initial remaining candidate set includes posts/supports, rectangular or
gate elements, color targets, ClassID 43 image planes, and the luminous-light
thermal proxy. Cone and hanger candidates must be selected from official
models and independently calibrated before entering L1 or L2.

## 8. Reproducible Scenario Set

Randomness is deterministic. A scenario is identified by course version,
width profile, difficulty level, and integer seed. The resolved scene stores
all generated positions, IDs, phases, amplitudes, and target assignments; the
same inputs must yield byte-identical resolved geometry.

Difficulty levels are cumulative:

- `L0`: empty course, coordinate and dual-UAV traversability baseline;
- `L1`: static cones, posts, and support/gate obstacles;
- `L2`: L1 plus a swinging suspended obstacle;
- `L3`: L2 plus one colored label, one QR target, and one thermal target;
- `L4`: competition-width stress scenarios with higher safe density and
  randomized task locations.

Generation uses bounded candidate slots rather than unrestricted random
coordinates. Each slot declares segment, `s` interval, `n` interval, support,
orientation range, and compatible asset roles. A deterministic constraint
solver selects within those bounds and rejects a seed if it cannot satisfy all
hard constraints within a bounded attempt count.

## 9. Obstacles and Task Targets

Static obstacles must not overlap walls, other obstacles, task observation
volumes, the takeoff exclusion zone, or landing approach zones. Clearance is
calculated from measured asset bounds plus the configured UAV safety envelope.
At least one traversable corridor must remain through each segment.

The swinging obstacle declares pivot, axis, arm length, body dimensions,
amplitude, period, phase, and full swept volume. The swept volume may not touch
the walls or permanently seal the channel. Temporal feasibility must include a
safe passage window rather than merely a collision-free static snapshot.

Task targets are attached to side walls or edge-mounted supports so they do not
consume the primary flight corridor. Each of the three types appears exactly
once in L3/L4. Segment, side, `s`, and mounting height vary by seed. For each
target the generator must retain at least one collision-free observation pose
within the relevant camera or sensor range and field-of-view model. Other
entities may not fully occlude the required observation ray set.

## 10. Landing Platforms and ArUco IDs

Two platform positions are fixed in course ENU and separated by `1.8 m` centre
to centre. Their approach volumes do not overlap the channel exit or each
other. Platform top faces are explicit support surfaces.

Each seed assigns two distinct IDs from an allowed ArUco `4x4_250` set. The
mapping is written to the resolved scene and receipt. The official ClassID 43
dynamic-image mechanism is used only after proving that simultaneous instances
can display distinct images. Until that is proven, the state remains
unsupported rather than silently showing duplicate IDs.

## 11. Automated Acceptance

### 11.1 Offline Geometry

The generator proves:

- three valid segments, required lengths, selected clear width, and turn radii;
- takeoff and landing zone dimensions;
- ID ownership and uniqueness;
- no static overlap or birth-zone intrusion;
- no permanent blockage after inflating geometry by the UAV safety envelope;
- dynamic swept-volume wall clearance and at least one passage window;
- three task types and valid observation poses;
- landing-platform spacing and marker dimensions;
- deterministic equality for equal seeds and valid diversity for different
  seeds.

An occupancy-grid or corridor search from both takeoff poses to both landing
approaches must succeed. L0 supplies a reference path; higher levels must prove
at least one path or time-parameterized passage remains.

### 11.2 Live UE Verification

For each static entity, at least three fresh metadata samples must agree. The
verifier checks:

- exact object ID, expected ClassID association, and object count;
- actor xy error no greater than `0.02 m`;
- support-face gap magnitude no greater than `0.02 m`;
- full-dimension error no greater than `0.02 m` per axis;
- yaw error no greater than one degree;
- finite, stable metadata and nondecreasing vendor timestamps;
- measured wall clearance, channel width, overlap, and exclusion zones.

Dynamic obstacles are sampled over at least one full period. Their measured
trajectory, period, extrema, and swept volume must match the resolved scene
within declared dynamic tolerances.

### 11.3 Sensor and Mission Levels

Evidence states are monotonic and explicit:

- `GENERATED_VALID`: offline geometry passed;
- `LOADED_VERIFIED`: commanded entities passed live UE metadata verification;
- `SENSOR_VERIFIED`: LiDAR/RGB/thermal-proxy observations agree with measured
  scene geometry;
- `MISSION_READY`: the applicable no-arm, navigation, task, and landing tests
  passed for this exact version/profile/level/seed and simulation instance.

Visual review cannot promote a geometry state. Offline PASS cannot promote a
live state, and one width profile cannot promote another.

## 12. Failure and Rollback

Loading is transactional over a declared project-owned ID range. The process is:

1. generate and validate a complete resolved scene;
2. inspect the current stack and require intended RflySim ownership;
3. remove only IDs owned by the previous course transaction;
4. place supports in dependency order;
5. read metadata and place dependent objects;
6. perform complete live verification;
7. publish the success receipt only after all checks pass.

On any hard failure, the loader deletes only IDs created by the current
transaction, writes commanded values, measured values, errors, seed, profile,
and simulation-instance provenance, and returns nonzero. It does not change the
base map, clear unrelated objects, arm, fly, retry with looser tolerances, or
fall back to ground fitting.

The current incorrect showcase IDs `13000..13009` are removed through the
bounded showcase-remove command before the first redesigned-map live trial.

## 13. Artifacts and Traceability

Each generated scenario produces:

- resolved ENU scene JSON;
- channel-local allocation JSON;
- top-down SVG preview with dimensions;
- occupancy/corridor validation report;
- support graph and expected world-bound report;
- deterministic artifact manifest containing both source-spec and scenario
  hashes.

Each live load produces a run-scoped receipt containing the stack ID,
simulation-instance ID, git commit, course/profile/level/seed, source and
resolved hashes, official model identities, commands, metadata samples,
measured world bounds, per-check errors, evidence state, and rollback outcome.

## 14. Scope and Delivery Order

The redesign is implemented in independently verifiable increments:

1. correct metadata world-bound and support-alignment mathematics;
2. remove branded assets and replace the near-field showcase with a
   support-aware self-verifying showcase;
3. implement the Z-course schema and L0 two-width generator;
4. implement transactional UE loading and live coordinate verification;
5. add L1 static obstacles and official-asset calibration;
6. add L2 dynamic obstacle and full-period verification;
7. add L3/L4 target randomization, observation checks, and ArUco assignment;
8. climb the existing no-arm, sensor, single-UAV, dual-UAV, and competition
   mission validation ladder.

No step may claim the evidence state belonging to a later step.
