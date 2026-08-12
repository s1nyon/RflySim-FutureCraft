# Official Asset Calibration Course Design

## 1. Purpose

Build a project-local, no-arm calibration workflow for official RflySim3D
assets before using them in predicted competition courses. Placement must be
based on measured geometry rather than model names, screenshots, or assumed
scale.

This is a prerequisite for static obstacles, swinging obstacles, unknown task
targets, randomized ArUco landing platforms, and competition metrics. It does
not claim to reproduce the unpublished competition layout.

## 2. Constraints and Protected Boundaries

- Use only assets and APIs distributed with the installed RflySim platform.
- Generated QR and ArUco images are allowed through the documented official
  dynamic-image interface.
- Treat installed RflySim, RflySimAPIs examples, CopterSim, PX4, and the
  `28com_sim`/`28com_uav` workspaces as read-only references.
- Do not alter PBL-1, `multi_uav_mission`, lifecycle internals, PX4,
  Faster-LIO, or EGO-Swarm during asset calibration.
- Calibration is no-arm and has no path that requests OFFBOARD, arming,
  takeoff, or mission execution.
- Create and remove only project-owned object IDs. Never clear the scene or
  infer ownership from a model name.
- Live measurements apply only to the recorded RflySim version, asset, scale,
  pose, sensor configuration, run ID, and stack instance.
- Do not overwrite external image files without a verified backup and explicit
  deployment. Verify restoration before considering cleanup complete.

## 3. Selected Approach

Create an independent asset calibration course before expanding the full
predicted competition map. Use official object metadata, RflySim-reported
bounding boxes, Mid360 point clouds, and RGB observations as separate evidence
layers.

This is preferred over immediate placement in the current course because an
asset's origin, ground offset, rendered dimensions, collision bounds, and
LiDAR-visible surface can differ. It is preferred over representing everything
with boxes because box-only scenes cannot exercise color, QR, or ArUco
perception.

A box representation remains available as an offline geometry surrogate. It
must be labelled `surrogate` and cannot establish live asset calibration.

## 4. Initial Asset Candidates

| Intended role | Official asset | Initial use |
| --- | --- | --- |
| Post or support | ClassID 813, `Pillar` | Static obstacle and support element |
| Rectangular element | ClassID 815, `Box` | Composite support and moving bar |
| Rectangular primitive | ClassID 818, `Box` | Alternative independently measured box |
| Ground obstacle | Official `carton_500`, `carton_750`, `carton_1000` | Static obstacle candidates |
| Colored target | ClassID 150 ring variants | Color recognition target |
| Colored target | ClassID 151 quad variants | Color recognition target |
| Image plane | ClassID 43, `Aruco_Custom` | ArUco and QR capability |
| Temperature proxy | ClassID 60 luminous light | Visual carrier plus simulated temperature truth |

The luminous light is not a thermal camera simulation. A later adapter may
associate simulated temperature data with it, but reports must distinguish
visual detection from temperature sensing.

No candidate is approved merely because its ClassID exists. Each intended role
must pass the relevant calibration gates.

## 5. Calibration Course Geometry

The calibration course uses the supported base scene without changing the
active map at object-load time. It places candidates on a deterministic metric
grid outside UAV spawn and protected course geometry.

The course specification defines:

- an ENU origin and rectangular calibration zone;
- an object-ID range distinct from the active predicted course;
- one-metre grid references and a known-size reference box;
- one isolated station per asset and scale sample;
- fixed RGB and Mid360 observation poses;
- spacing that prevents bounding boxes and point clusters from overlapping;
- a dynamic-test station whose full motion envelope stays inside the zone.

The generator rejects layouts overlapping UAV spawn envelopes, active course
objects, other stations, or the zone boundary. Before live bounds exist,
station spacing uses declared conservative bounds.

## 6. Coordinate and Dimension Model

Every observation preserves three notions of geometry:

1. **Commanded geometry:** pose, ClassID, and scale passed to the official API.
2. **Reported geometry:** `PosUE`, `boxOrigin`, `BoxExtent`, and attitude returned
   by the official object-query interface.
3. **Observed geometry:** point-cloud extent and RGB observation from declared
   sensor poses.

Profiles store dimensions as full extents in metres and retain raw
`BoxExtent`, which is a half extent. Ground offset is calculated from the
lowest reported or observed point relative to the placement plane. The profile
never substitutes `PosUE` for `boxOrigin`.

Vendor/NED values are converted once at the API boundary into project ENU.
Reports retain raw and converted values so axis or sign errors remain auditable.

## 7. Asset Profile Contract

Each asset and scale sample produces a profile containing:

```text
schema version
asset identity and official source path
ClassID / variant / intended roles
commanded pose and scale
raw PosUE / boxOrigin / BoxExtent
converted ENU centre and full dimensions
ground offset and axis orientation
RGB result and artifact reference
LiDAR result, measured extent, point count, and artifact reference
collision status, if separately measured
RflySim version and relevant asset checksums
sensor configuration checksums
run ID, stack instance ID, timestamps, and tool version
approval state and explicit rejection reasons
```

Approval states are:

- `DECLARED`: candidate exists only in configuration.
- `METADATA_MEASURED`: object-query bounds were received and validated.
- `LIDAR_MEASURED`: stable point-cloud visibility and extent were measured.
- `RGB_MEASURED`: required visual content was observed.
- `ROLE_APPROVED`: all gates for a particular role passed.
- `REJECTED`: a gate failed; reasons and evidence are retained.

An asset can be approved for one role and rejected for another. A colored plane
may be a visual target without being a physical obstacle.

## 8. Static Calibration Workflow

For each candidate and selected scale:

1. Validate configuration, ID ownership, station geometry, and source asset
   without launching or changing a map.
2. Load one candidate through the official placement API.
3. Collect repeated `PosUE`, attitude, `boxOrigin`, and `BoxExtent` samples.
4. Reject missing, non-finite, inconsistent, or stale metadata.
5. Observe it with Mid360 inside the expected station volume. Record point
   count, update rate, extent, and deviation from reported bounds.
6. Capture RGB evidence from a fixed pose. For visual targets, verify sufficient
   projected size and expected color or code content.
7. Remove only the candidate's owned ID and verify disappearance.
8. Write the profile and artifact manifest atomically.

Metadata, LiDAR, and RGB failures remain separate. An overall result cannot
hide a failed evidence layer.

## 9. Dynamic Obstacle Calibration

Dynamic testing starts only after the selected asset is approved as a static
LiDAR obstacle. The first motion model is a deterministic planar pendulum:

```text
angle(t) = amplitude * sin(2*pi*t/period + phase)
position(t) = pivot + pendulum geometry derived from angle(t)
```

The specification records pivot, length, amplitude, period, phase, update rate,
and full swept envelope. The controller updates only the owned object ID.

Dynamic evidence measures command-to-observation latency, achieved rate,
dropped updates, position error, LiDAR continuity, observed envelope, and
minimum remaining clearance.

The object is a kinematic scene entity, not a claim of full rigid-body pendulum
physics. It is suitable for testing detection and replanning only after its
motion and sensor-continuity gates pass.

## 10. ArUco and QR Image Handling

ClassID 43 uses the official dynamic-image mechanism. Project tools first
generate ArUco 4x4_250 and QR images in a project-owned directory, recording
dictionary, ID or payload, pixels, physical size, border policy, and checksum.

A separate explicit deploy helper may copy an approved image to the installed
path expected by RflySim. It must:

1. resolve and verify the exact destination;
2. create a byte-for-byte run-scoped backup;
3. record source, destination, and checksums;
4. refuse ambiguous deployment or backup state;
5. restore the original during normal cleanup and verify its checksum.

A failed restore is reported and never hidden by automatic retry or destructive
cleanup.

Calibration explicitly tests whether multiple ClassID 43 instances can display
different images simultaneously. Until proven, multiple random landing IDs are
an open capability. If only one global image is supported, the first course
uses one active visual marker at a time or another documented official image
asset and does not claim simultaneous random-ID coverage.

## 11. Integration with Predicted Courses

`predicted_narrow_course_v1.json` and PBL-1 remain unchanged during calibration
development. A later schema version references stable asset-profile IDs instead
of embedding assumed ClassIDs and scales.

Course objects use centreline-relative placement:

```text
s: distance along the corridor centreline
d: signed lateral offset
h: height above the local placement plane
yaw_offset: orientation relative to the centreline tangent
```

The generator converts these values to ENU and validates the calibrated box or
dynamic envelope. It rejects:

- wall, ceiling, floor, takeoff-zone, or platform intersections;
- remaining free space smaller than the vehicle envelope plus safety margin;
- targets outside calibrated camera orientation and distance limits;
- dynamic envelopes leaving their allowed region;
- landing-platform spacing that violates the guide;
- assets not approved for the requested role.

Random layouts use an explicit seed. Every run stores the resolved layout as
well as the seed for exact reproduction.

## 12. Competition-Oriented Metrics

Calibration enables but does not prove competition performance. The later
course evaluator records at least:

- takeoff and corridor-entry time;
- traversal time and completed segments;
- collisions and unexpected OFFBOARD loss;
- minimum wall, obstacle, and inter-UAV clearance;
- replanning attempts, successes, and latency;
- dynamic-obstacle avoidance success;
- target detection, classification, localization error, and duplicate rate;
- ArUco detection range, pose error, landing error, and platform ID;
- provenance for course seed, profiles, images, code, and stack instance.

Thresholds stated by the competition guide use its values. Unknown thresholds
remain unset and are reported as measurements rather than invented pass rules.

## 13. Failure Handling and Safety

- Missing assets, invalid IDs, stale metadata, or inconsistent conversion fail
  closed before sensor or dynamic testing.
- RGB-visible but LiDAR-invisible models cannot be approved as obstacles.
- LiDAR-visible but unreadable models cannot be approved as visual targets.
- Point-cloud measurement never changes Faster-LIO or EGO parameters.
- No-arm readiness failure stops the run and never escalates to arming.
- Unknown or stale processes are reported and never killed by name.
- External assets are not modified during generation, offline tests, or DryRun.
- Cleanup affects only recorded owned IDs and explicitly deployed images with
  verified backups.

## 14. Test and Validation Ladder

### T0 — Offline contracts

- schema validation and deterministic generation;
- unique owned IDs and station non-overlap;
- coordinate conversion and half/full-extent unit checks;
- centreline placement and swept-envelope geometry;
- random-seed reproducibility and impossible-layout rejection;
- image generation, backup, restore, and checksum logic using temporary files;
- relevant repository, Stage 7, and Stage 8 contracts remain green.

### T1 — RflySim metadata, no sensors required

- each configured ClassID creates successfully;
- repeated metadata samples are finite and stable;
- bounds and ground offsets are recorded;
- owned-object removal is verified;
- the active map is not changed.

### T2 — Live no-arm sensor calibration

- current stack and run-scoped readiness are valid;
- obstacle candidates are visible in isolated UAV LiDAR data;
- visual candidates are observable in RGB at declared poses;
- artifacts and checksums are current-run scoped;
- no mission, OFFBOARD, or arming request occurs.

### T3 — Dynamic no-arm calibration

- the pendulum completes deterministic cycles;
- command, metadata, and LiDAR streams remain continuous;
- measured motion remains inside the validated envelope;
- cleanup removes the owned dynamic object.

### T4 — Predicted-course integration

- only `ROLE_APPROVED` profiles are accepted;
- standard, stress, and seeded-random courses generate deterministically;
- obstacle, target, and landing geometry passes validation;
- dual sensor identity/isolation and no-arm checks pass in the scene.

Armed navigation is a separate, explicitly authorized simulation-only step. It
is not required to approve calibration tooling.

## 15. Deliverables

- versioned asset-candidate specification;
- pure geometry, conversion, and profile validation modules;
- calibration scene generator and official-API loader;
- read-only object-metadata recorder;
- no-arm LiDAR/RGB probes;
- dynamic-obstacle controller and recorder;
- project-local ArUco/QR generation and explicit deploy/restore tooling;
- deterministic reports, manifests, and SVG previews;
- focused offline tests and supported validation entries;
- documentation separating declared, measured, approved, and rejected assets.

## 16. Non-Goals

- predicting the exact unpublished map;
- importing custom 3D meshes or installing a UE Editor workflow;
- changing the protected PBL-1 strategy;
- tuning EGO-Swarm, Faster-LIO, or PX4 for uncalibrated assets;
- claiming luminous RGB content is real thermal sensing;
- claiming collision geometry without a dedicated collision test;
- live arming or autonomous flight during calibration.

## 17. Completion Criteria

Calibration is complete when:

1. every initial candidate has a reproducible profile and explicit evidence
   states;
2. at least one official asset is approved as a static obstacle;
3. at least one official asset is approved for deterministic dynamic motion;
4. colored targets and ClassID 43 have RGB evidence;
5. simultaneous distinct ArUco instances are proven or recorded unsupported
   with a tested fallback;
6. deployed files and scene objects have bounded, verified cleanup;
7. a predicted course can consume approved profiles without changing PBL-1
   defaults;
8. relevant offline and live no-arm evidence is recorded without unsupported
   claims of flight or competition readiness.
