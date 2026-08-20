# Coordinate-Verifiable Basic Course Design

## 1. Outcome

Create `competition_basic_course_v1`, a new basic Z-shaped flight course whose
geometry can be generated, loaded, and verified from machine-readable data
without using screenshots or human visual judgement as coordinate evidence.

The delivery target is one `FIRST LIVE PASS` on the new course:

1. generate and validate the course offline;
2. load it into RflySim and verify the measured scene without arming;
3. pass current-run dual-UAV readiness;
4. complete one dual-UAV takeoff, full route, landing, and disarm run with no
   collision or unexpected OFFBOARD loss.

The existing `predicted_narrow_course_v1` remains unchanged as the PBL-1
rollback baseline. The new course is introduced beside it and does not become
the default merely because its first live run succeeds.

## 2. Scope

The new course contains only:

- the existing verified flat `SLAMScene` terrain deployment;
- an obstacle-free two-UAV takeoff zone;
- three straight corridor segments joined by two 90-degree turns in a balanced
  Z topology;
- simple, static corridor walls;
- an unobstructed exit and two separated nominal AUTO.LAND areas;
- two takeoff poses, a generated navigation route for each UAV, and a bounded
  geofence.

The clear corridor width is `1.5 m`. The centreline turn radius is `1.65 m`, so
the inner wall radius is `0.90 m`. Wall height is `2.5 m`. Exact numeric
endpoints and zone bounds live only in the versioned source specification and
are copied into the generated validation report.

The following are explicitly deferred:

- QR codes, colored labels, thermal targets, and target randomization;
- cones, posts, gates, or other competition-specific static obstacles;
- swinging or otherwise dynamic obstacles;
- D435i/RGB/depth integration and all perception work;
- ArUco platforms and precision landing;
- simultaneous corridor entry, new coordination policy, and mission-strategy
  changes;
- the seven-asset showcase from the superseded broad foundation plan;
- tuning EGO-Swarm, Faster-LIO, PX4, or the protected mission executor.

## 3. Safety and Ownership Boundaries

- ENU metres are the only design truth. NED conversion occurs only in the UE
  command adapter.
- The base map remains `SLAMScene`; the loader does not change maps.
- The course uses a dedicated project-owned object-ID range `14000..14999`.
- Live mutation is restricted to RflySim window `0` and IDs in the declared
  course transaction.
- The loader never uses `sendUE4PosScale2Ground`, system-wide clear commands,
  name-based process killing, `wsl --shutdown`, implicit arming, or automatic
  force retry.
- Existing `12000..12999` PBL course objects and `13000..13009` calibration
  objects are not silently claimed or deleted by the new loader.
- Changes stay in agent-owned map/tooling/test files. Existing protected
  mission behavior and lifecycle internals remain unchanged unless fresh
  evidence proves a separate change is unavoidable.

## 4. Architecture

### 4.1 Versioned ENU Source

`config/maps/competition_basic_course_v1.json` is the sole design source. It
declares:

- schema version, course name, frame, units, and base map;
- owned ID range and static primitive calibration profile;
- the expected existing flat-terrain artifact hashes and context;
- wall height, thickness, and clear corridor width;
- takeoff zone, takeoff poses, centreline lines/arcs, exit/landing zone;
- per-UAV world-route samples, spawn-relative local-route conversion, and
  route-generation spacing rules;
- vehicle safety envelope and geofence margin;
- offline and live tolerances.

No coordinate may be recovered from an SVG, screenshot, console log, or UE
camera view. Generated artifacts contain the source hash, and consumers reject
hash mismatches.

### 4.2 Calibrated Static Primitive

All course walls use one already calibrated official RflySim static primitive,
selected by its exact UE command type and scale profile from stable live
metadata. Placement uses the primitive's measured local box origin, half
extent, actor transform, and command scale rather than conflating UE command
type `1000813`, catalog ClassID `813`, or an assumed native cube.

The geometry module transforms all eight local bounding-box corners to compute
world bounds. Desired wall dimensions determine scale from calibrated measured
dimensions. Actor Z is solved so the measured bottom support face is aligned to
terrain `z=0`. Yaw is included in the transformed-corner calculation.

If the exact command-type/scale calibration profile is absent, unstable, or
cannot reproduce the desired dimensions within tolerance, generation/load
fails closed. Current metadata does not expose a trustworthy ClassID field, so
the live verifier does not claim to verify one.

### 4.3 Pure Geometry Model

A pure Python module parses the source and produces a resolved course model:

- sampled centreline and left/right wall paths;
- deterministic wall boxes with stable IDs;
- takeoff poses, world route points, per-UAV spawn-relative local route points,
  two exit/landing goals, and geofence;
- expected actor poses, scales, world bounds, and support gaps;
- a collision-inflated 2D traversability model.

Offline validation proves:

- all numbers are finite and all IDs are unique and in range;
- exactly three straight corridor segments and two continuous turns exist;
- minimum clear width is `1.5 m` after wall thickness is accounted for;
- wall bottoms align to `z=0` and no wall overlaps the takeoff or landing area;
- both takeoff poses have the configured separation and vehicle-envelope
  clearance;
- each generated world route lies inside the traversable corridor and connects
  its takeoff pose to its own non-conflicting exit/landing area;
- each local planner goal equals the corresponding course-world route point
  minus that UAV's world spawn under the existing verified axis convention,
  and the report proves the world-to-local-to-world round trip;
- every route point and geofence bound is derived from the same source model;
- equal input bytes produce byte-identical artifacts.

### 4.4 Deterministic Artifacts

Generation writes a dedicated directory under
`generated/competition_basic_course_v1/` containing:

- `resolved_scene.json`;
- `navigation_routes.json` containing authoritative world and per-UAV local
  routes;
- a generated executor input in the existing protected flight-plan contract;
- `geofence.json`;
- `validation_report.json`;
- `course_preview.svg` as a non-authoritative aid;
- `artifact_manifest.json` with SHA-256 values.

The existing verified flat-terrain bytes and deployment flow are reused by
hash; this course does not generate or deploy a second pair of same-named
`SLAMScene.png/.txt` files. The historical `planning_points.json` is a sampled
wall/platform point-cloud artifact and is not reused or redefined as a flight
route.

The existing narrow-course geometry, terrain, preview, and reporting code is
reused where its contracts are correct. New code is separated where changing
the old implementation would risk PBL-1.

The new course has a focused aggregate validator rather than redefining old
Stage 8 fixtures. If a static reference cloud is required for existing health
inspection, the new course may publish the compatibility topic
`/predicted_narrow_course/global_cloud`; this is documented as a compatibility
alias, while the receipt and provenance still name the new course and hash.

### 4.5 Transactional UE Load and Automatic Verification

The new loader is DryRun-first. Before live mutation it requires:

- a generated report matching the source and artifact hashes;
- window ID exactly `0`;
- the expected `SLAMScene` context;
- no duplicate or out-of-range object IDs.

For a live transaction it removes only IDs explicitly listed in the previous
successful `competition_basic_course_v1` receipt. Missing or inconsistent
receipt ownership fails closed; the loader never scans or clears the full ID
range. It verifies absence through fresh metadata/nonresponse, sends the
resolved static wall commands, and immediately samples official object
metadata. Each object requires three fresh stable samples.

The verifier checks:

- object ID and exact expected command transaction;
- actor XY and Z error at most `0.02 m`;
- local oriented-dimension error at most `0.02 m` per axis, computed from the
  transformed eight-corner box rather than comparing yaw-inflated AABB axes;
- wrapped yaw error at most `1 degree`;
- bottom support gap at most `0.02 m`;
- measured wall clearance and minimum channel width from oriented wall
  polygons, not actor centres or axis-aligned bounding boxes;
- measured objects remain outside takeoff and landing exclusion zones.

The flat terrain is validated by expected artifact hash and `SLAMScene`
context, not by claiming terrain actor metadata. Wall support gaps are measured
against the declared design plane `z=0`.

Success produces a run-scoped `LOADED_VERIFIED` receipt containing stack ID,
simulation-instance ID, git commit, source/artifact hashes, commands, metadata
samples, measured bounds, and per-check errors. Failure destroys only IDs whose
creation was acknowledged in the current transaction, verifies their absence,
records rollback results, returns nonzero, and does not authorize flight. An
incomplete rollback has its own failure state and cannot publish a success
receipt.

## 5. Flight Integration

The new course gets dedicated generate/load wrappers while reusing the existing
dual-UAV stack, Faster-LIO, EGO-Swarm, setpoint bridge, readiness probe, event
recorder, and score summary. The live stack selector and protected flight
runner are parameterized behind an explicit new-course option instead of
copying their safety chain. Their default remains
`predicted_narrow_course_v1`, so no existing invocation changes behavior.

This opt-in selector is a Yellow/change-gated launcher boundary. The change is
limited to choosing the course source, generated geofence, route adapter,
loader, and `COURSE_READY` receipt. Rollback is removal of the selector and new
course files; validation includes default-PBL DryRun equivalence plus the new
course focused contracts. No lifecycle ownership or stop semantics change.

The generated routes are adapted by a new course-specific wrapper into the
existing mission flight-plan contract. The protected mission implementation is
not redefined. If that contract cannot accept an external generated plan, the
smallest adapter change is treated as a Yellow/change-gated boundary with
focused tests and rollback, rather than silently changing mission behavior.

No new coordination semantics, target behavior, or planner tuning is
introduced. Both UAVs take off; UAV1 navigates while UAV2 waits, UAV1 then
holds at its separated exit goal while UAV2 navigates, and both finally land at
their distinct nominal goals using the existing AUTO.LAND behavior. This is a
map/traversability acceptance, not Phase 3 simultaneous-entry acceptance.

The route uses look-safe centreline samples with goal spacing compatible with
the current EGO chain. Takeoff altitude, navigation altitude, goal tolerances,
OFFBOARD policy, watchdog, and landing behavior remain at their protected
values unless the source geometry alone makes a route invalid; such a conflict
fails the design rather than silently retuning the flight stack.

The existing flight runner and watchdog currently contain predicted-course
source and geofence constants. The new-course option must inject the generated
source hash and geofence into both; using the old constants with the new map is
a hard pre-arm failure. Provenance, route input, watchdog geofence, and live
load receipt must all identify the same course, stack, simulation instance, and
source hash.

## 6. Accelerated Validation Ladder

To meet the same-day target, validation is limited to evidence that directly
distinguishes map correctness and flight safety:

1. the new-course focused aggregate validator covering world bounds, schema,
   geometry, artifacts, loader, verifier, flight plan, new-course DryRun, and
   default-PBL selector equivalence;
2. the existing Stage 8 aggregate validator because the change touches its
   course-loading, geofence, route, and planner/control boundaries;
3. loader DryRun with exact object list and no mutation;
4. one no-arm live load with automatic metadata verification;
5. current-run dual-UAV topology, Mid360, odometry, TF, freshness, isolation,
   and stationary-stability readiness gates within the existing fresh window;
6. EGO startup and topic probe PASS for the new-course route/control chain;
7. one simulation-only, explicitly authorized dual-UAV full flight;
8. artifact review for every route goal, landing/disarm, collision engine
   enabled, unexpected OFFBOARD loss zero, and timeout count zero. Because a
   reliable UE collision topic is not assumed, recorded trajectory-to-measured-
   wall clearance must also remain greater than the vehicle envelope plus
   configured safety margin.

Stage 6 and unrelated perception/calibration suites are not rerun mechanically.
A separate single-UAV run is omitted because the flight/control chain is
unchanged and the no-arm measured geometry plus the staggered full-flight run
exercise the changed boundary. Any no-arm geometry failure, readiness failure,
planner rejection, collision, watchdog event, or OFFBOARD loss stops the fast
path and reopens the appropriate lower validation level.

One successful fresh-instance run earns only `FIRST LIVE PASS`. Three fresh
successful runs are still required before promoting the course to a protected
or repeatable baseline.

## 7. Live Authorization Points

The agent may run offline tests and all DryRuns without additional approval.
Before state-changing live work, the operator must explicitly authorize:

- starting the live stack if a new stack is required;
- removing an existing project-owned new-course transaction;
- simulation-only arming and OFFBOARD flight;
- executing the manifest-owned stop sequence.

Unknown/stale ownership or occupied ports fail closed. The known WSL PGID stop
defect is not bypassed with broad process killing. If it prevents a clean fresh
instance, the run is reported blocked rather than made unsafe to meet the
calendar target.

At design time the selected historical stack has no owned live processes and
its key ports are free, but inspection reports stale PID reuse and therefore
fails closed. It is not a flight-authorizing instance; today's live acceptance
requires an explicitly authorized fresh stack.

## 8. Completion Criteria

The same-day objective is complete only when all of the following belong to the
same source hash and live simulation instance:

- offline state `GENERATED_VALID`;
- live state `LOADED_VERIFIED` without visual-coordinate assumptions;
- readiness PASS for both UAVs;
- both UAVs arm only through the simulation safety policy;
- both take off, traverse every generated route goal, land, and disarm;
- collision count where available, unexpected OFFBOARD loss count, and timeout
  count are zero, and recorded wall clearance remains above the configured
  inflated vehicle envelope;
- run-scoped artifacts and a `FIRST LIVE PASS` evidence note are preserved;
- the old PBL course remains available and unchanged.

If implementation and offline/no-arm validation finish but the live stack is
unavailable or live authorization is not granted, the result is explicitly
handed off as `LIVE ACCEPTANCE PENDING`, not as completion.
