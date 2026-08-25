# Competition Course V2 Design

## 1. Purpose and status

Build one project-owned `competition_course_v2` development map on the accepted
`f23de934205b6776ef0531d46c26444bf9f7f65e` infrastructure baseline. The map is
deterministic, explicitly selected, regenerable from a clean checkout, and usable
for later localization, planning, perception, and coordination experiments.

This is a **DEVELOPMENT MAP**, not an official final competition layout. It does
not establish `competition_world`, change either Faster-LIO origin, modify the
existing mission, or replace the protected `predicted_narrow_course_v1` default.

## 2. Requirements authority

The following values are `OFFICIAL`, as summarized from competition guide 2.1
in `docs/current/competition-roadmap.md`:

- at least two UAVs and at least as many unobstructed takeoff points;
- at least three scored narrow-channel segments;
- each channel segment is at least 3 m long;
- clear channel width is no greater than 1.5 m;
- turn radius is no greater than 1 m;
- static obstacles and a swinging suspended dynamic obstacle;
- landing platforms outside the channel, one per UAV, with centres more than
  1.5 m apart;
- ArUco dictionary `4x4_250`, with marker size described inconsistently as
  0.5 m and 0.6 m by the guide.

The exact course layout, obstacle poses, dynamic parameters, target asset, and
marker IDs are `PREDICTED` or `CONFIGURABLE`. The V2 default marker size is
0.6 m and remains one JSON parameter. Standard QR is not implemented because
the current map milestone requires an ArUco landing target; the later mission
target may select QR after its exact competition asset contract is known.

## 3. Selected architecture

Use an independent V2 pipeline which follows the current pattern without
changing V1 geometry modules:

```text
config/maps/competition_course_v2.json
  -> competition_course_geometry.py
  -> competition_course_artifacts.py
  -> generated/competition_course_v2/*
  -> competition_course_ue_loader.py
  -> competition_course_motion.py (owned process)
  -> RflySim SLAMScene
```

The JSON is the only authored geometry source. Generated PNG terrain, TXT
calibration, SVG preview, resolved scene, planning points, marker PNGs,
validation report, and artifact manifest are derived and ignored artifacts.

The loader creates only the V2-owned IDs `15000..15999`. A run-scoped receipt
records exact created IDs. Reload removes only IDs proven by a matching prior
receipt; it never range-clears or touches V1 IDs `12000..12999`.

## 4. Course geometry

All authored positions are ENU metres. Ground is `z=0`; conversion to vendor
NED happens once at the UE API boundary.

### 4.1 Takeoff area

- bounds: `x=[0,5]`, `y=[-2.5,2.5]`;
- UAV1: `(2.0,-0.7,0)`, yaw `0`;
- UAV2: `(2.0,0.7,0)`, yaw `0`;
- separation: `1.4 m`;
- no obstacle swept or static footprint enters this zone.

### 4.2 Three-segment channel

The centreline is:

1. Section A: line `(5,0)` to `(12,0)`, length `7 m`, width `1.5 m`;
2. left 90-degree arc, centre `(12,0.9)`, radius `0.9 m`, width `1.5 m`;
3. Section B: line `(12.9,0.9)` to `(12.9,5.9)`, length `5 m`, width `1.4 m`;
4. right 90-degree arc, centre `(13.8,5.9)`, radius `0.9 m`, width `1.4 m`;
5. Section C: line `(13.8,6.8)` to `(20.8,6.8)`, length `7 m`, width `1.5 m`.

Walls are `2.5 m` high and `0.15 m` thick. Arc tessellation has maximum chord
error `0.02 m`. The long straight, repetitive wall geometry, and two opposite
turns provide a reasonable future localization comparison without creating an
extreme benchmark.

### 4.3 Exit and landing area

- landing bounds: `x=[20.8,28.0]`, `y=[3.8,9.8]`;
- platform centres: `(24.5,5.9,0)` and `(24.5,7.7,0)`;
- platform size: `0.9 x 0.9 x 0.10 m`;
- centre spacing: `1.8 m`;
- marker size: `0.6 x 0.6 m` on each platform top face.

This open area also reserves space for later crossing-trajectory experiments;
no such coordination experiment is part of V2 acceptance.

## 5. Static obstacles and target slot

Two deterministic primitive obstacles use the already accepted SLAMScene box
mechanism and explicit collision-enabled scene mode:

- `static_box_a`: Section A, centre `(9.0,0.30,0.45)`, size
  `0.35 x 0.35 x 0.90 m`;
- `static_pillar_b`: Section B, centre `(12.60,3.20,0.60)`, size
  `0.30 x 0.30 x 1.20 m`.

Validation inflates obstacles by the configured UAV horizontal radius and
safety margin, then proves that at least one cross-section interval remains.
It does not call this proof an EGO mission guarantee.

`mission_target_slot` is a configurable zone centred at `(18.8,7.35,1.2)` with
size `0.8 x 0.3 x 0.8 m`, mounted outside the primary traversable strip. Its
asset remains `placeholder`; no color, QR payload, temperature, detector, or
mission action is invented.

## 6. Dynamic obstacle

One kinematic pendulum occupies Section C. Its source contract is:

```text
object_id: 15120
pivot: (17.2, 6.8, 2.4)
length: 1.2 m
amplitude: 30 deg
period: 4.0 s
phase: 0 rad
update rate: 20 Hz
body size: 0.25 x 0.25 x 0.70 m
motion plane: channel lateral/vertical
```

For elapsed controller time `t`:

```text
angle(t) = amplitude * sin(2*pi*t/period + phase)
y(t) = pivot_y + length*sin(angle(t))
z(t) = pivot_z - length*cos(angle(t))
```

The controller updates only ID `15120`, logs commanded monotonic time and pose,
and is launched through the existing Windows at-creation registrar. Standard
stop therefore uses the unchanged PID/start-time/fingerprint safety model.
Offline validation proves positive period/rate, bounded amplitude, swept-volume
wall clearance, and at least one temporal passage window. Live acceptance
requires observed poses at three or more times and an approximately correct
period and extrema; a `dynamic:true` label alone cannot pass.

## 7. ArUco asset deployment

OpenCV generates two deterministic `DICT_4X4_250` marker PNGs from configured,
distinct IDs. RflySim ClassID 43 reads the installed fixed path
`D:/PX4PSP/RflySim3D/RflySim3D/Content/Aruco/Aruco.png` when creating a marker.

For each marker, the loader:

1. verifies the exact source, destination, and destination checksum;
2. creates a byte-identical run-scoped backup;
3. atomically deploys the generated PNG and verifies its checksum;
4. creates and sizes the declared ClassID 43 instance;
5. immediately restores the original file in `finally` and verifies checksum;
6. records source, backup, deployed, and restored hashes in the receipt.

Any ambiguous backup state, copy error, object creation error, or failed restore
returns nonzero. The loader never leaves a reported successful receipt unless
the installed file is restored. Live RGB evidence must prove both instances
retain the intended distinct images simultaneously; otherwise ArUco acceptance
is blocked rather than silently showing duplicate IDs.

## 8. Deployment, selection, and protected defaults

New entry points generate, validate, deploy the flat SLAMScene CopterSim
terrain, load V2, and start V2 explicitly. The terrain deploy helper uses the
existing verified backup/copy/byte-compare policy with a V2 output directory.

`live_stack_start.ps1` gains one validated course selector:

```text
-Course predicted_narrow_course    # default, unchanged
-Course competition_course_v2      # explicit opt-in
```

The selector changes only which startup batch is placed in the run-scoped
scheduled task. Manifest schema, ownership, readiness statuses, launch order,
stop behavior, and default map remain unchanged.

The Stage 7 sensor runner gains an explicit `full` diagnostic selection while
keeping `lidar_only` as its default. V2 RGB validation runs no-arm in `full`;
planner smoke and old-map regression use `lidar_only`. This prevents the known
full-sensor rendering load from becoming a flight-baseline dependency.

## 9. Validation and evidence states

Evidence is kept in four distinct levels:

- `STRUCTURAL_VALIDATION`: schema, geometry, IDs, clearance, motion, marker,
  determinism, and artifact checks pass offline;
- `LIVE_SENSOR_VALIDATION`: exact V2 receipt, dual spawn, wall/static/dynamic
  LiDAR observations, RGB marker frames, IMU, and observed motion pass;
- `PLANNER_SMOKE`: dual Faster-LIO odometry/cloud and basic EGO trajectory
  production pass without immediate fatal errors;
- `FULL_MISSION`: optional and not required for V2 acceptance.

Offline tests use synthetic clients and temporary directories. They cover
strict schema parsing, non-finite inputs, unique owned IDs, no spawn overlap,
channel continuity, no permanent blockage, pendulum motion/extrema, distinct
markers, reversible image deployment, deterministic byte equality, stale
report rejection, receipt-owned cleanup, loader dry-run, lifecycle default and
opt-in selection, and old V1 contracts.

Live validation uses the manifest lifecycle and never arms for map acceptance.
It records the stack/run identity, object receipt, motion samples, topic rates,
point counts, RGB artifacts, and clean-stop proof. The old map then runs its
existing generate/deploy/load path and one protected full-route regression
because the opt-in course selector touches a shared launcher boundary.

## 10. Failure handling and rollback

- Generation and DryRun never modify installed assets or start processes.
- Invalid geometry, missing assets, stale reports, or hash mismatch fail before
  scene mutation.
- Scene rollback destroys only IDs created by the current transaction.
- Dynamic-controller registration failure is fatal; V2 is not marked READY.
- ArUco restoration failure is a hard blocker and is reported with exact paths
  and hashes; no broad filesystem or process cleanup is allowed.
- Unknown/stale lifecycle processes continue to fail closed.
- Rollback of this feature removes V2 files and the two opt-in selectors; the
  unchanged default continues to select `predicted_narrow_course`.

## 11. Explicit non-goals

No OpenVINS, shared competition TF, EGO-Swarm conflict experiment, dynamic
entry arbitration, coordinator, ArUco detector, QR detector, precision landing,
new mission FSM, mission rewrite, planner tuning, Faster-LIO tuning, PX4/MAVROS
change, or full V2 mission is implemented.
