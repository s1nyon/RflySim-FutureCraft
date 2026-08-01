# Predicted Narrow-Course Map V1 Design

## Goal

Create a usable first-version competition prediction map for the indoor
narrow-passage multi-UAV challenge. The map contains only the takeoff area, a
narrow passage, and the landing area. Target labels, QR recognition, heat
sources, mission actions, internal static obstacles, and moving obstacles are
deferred.

The implementation is project-local to `future_aircraft_sim`. It treats
`28com_sim`, RflySim3D, CopterSim, and the general RflySim examples as
read-only references.

## Requirements Taken From the Competition Guide

- The environment is indoor and GPS-denied.
- At least two UAVs operate in the same course.
- The narrow passage is at least 3 m long.
- Passage clear width is no greater than 1.5 m.
- Turn radius is no greater than 1 m.
- The takeoff area is flat and unobstructed, with at least as many takeoff
  points as UAVs.
- The landing area is outside the passage and contains at least as many
  landing platforms as UAVs.
- Landing-platform center spacing is greater than 1.5 m.

The guide describes 60 cm square ArUco landing markers, but V1 creates only
the physical landing platforms. Marker textures and recognition are deferred.

## Selected Approach

Use a Python-driven dynamic RflySim scene on a flat base map. One versioned
JSON course specification is the source of truth for rendering, ROS planning
geometry, spawn/landing coordinates, validation, and generated CopterSim
terrain files.

This approach is selected over an immediately cooked UE map because the real
competition layout is not published and dimensions will need rapid iteration.
It is selected over the 28com random-map generator because that generator
publishes planning point clouds but does not create the matching RflySim3D
objects seen by cameras and LiDAR.

A later version may bake the approved layout into UE5 without changing the
course specification or mission-facing coordinates.

## V1 Geometry

All authored coordinates use a project ENU world frame in metres. The loader
performs the conversion required by the RflySim API. Ground altitude is 0 m.

### Takeoff area

- Rectangle: 5 m by 5 m.
- Bounds: `x = [-2.5, 2.5]`, `y = [-2.5, 2.5]`.
- UAV1 takeoff point: `(0.0, -0.7, 0.0)`.
- UAV2 takeoff point: `(0.0, 0.7, 0.0)`.
- Initial heading: positive X.
- Takeoff-point separation: 1.4 m.
- The area contains no obstacles other than optional flat visual point
  markers, which are non-colliding and disabled by default.

### Narrow passage

The S-shaped passage begins at the positive-X edge of the takeoff area and has
three straight sections joined by two opposite 90-degree turns:

1. Straight east from `(2.5, 0.0)` to `(7.0, 0.0)`, clear width 1.5 m.
2. Left turn with centreline radius 0.9 m.
3. Straight north from `(7.9, 0.9)` to `(7.9, 4.0)`, clear width 1.4 m.
4. Right turn with centreline radius 0.9 m.
5. Straight east from `(8.8, 4.9)` to `(13.3, 4.9)`, clear width 1.5 m.

The resulting centreline is approximately 14.9 m long. Walls are 2.5 m high
and 0.15 m thick. V1 has no ceiling so the map remains easy to inspect and
debug. Curves are represented by sufficiently short wall segments that the
maximum chord error is no more than 2 cm.

For the previously used simulated aircraft, the design assumes a conservative
0.45 m horizontal collision envelope. The 1.4 m section therefore provides
approximately 0.475 m nominal side clearance when centred. Two aircraft are
not expected to pass side-by-side inside the corridor; mission coordination
must sequence their entry.

### Landing area

- Rectangle: 5 m by 4 m immediately beyond the passage exit.
- Bounds: `x = [13.3, 18.3]`, `y = [2.9, 6.9]`.
- Two platforms, each 0.8 m by 0.8 m and 0.1 m high.
- Platform centres: `(16.0, 3.9)` and `(16.0, 5.9)`.
- Platform centre spacing: 2.0 m.

The platforms reserve a centred 0.6 m by 0.6 m marker surface for the later
ArUco 4x4_250 implementation.

## Architecture and Outputs

### Course specification

`config/maps/predicted_narrow_course_v1.json` contains schema version, units,
base-map name, wall dimensions, centreline geometry, zones, takeoff poses,
landing poses, object identifiers, and safety-envelope parameters. Runtime
code rejects unknown schema versions, duplicate object IDs, non-finite values,
and geometry that violates the guide constraints.

### RflySim scene loader

A Windows-side Python loader reads the course specification and creates the
floor boundary, walls, and platforms through `UE4CtrlAPI`. It uses deterministic
object IDs, supports an idempotent reload, and can remove only the IDs owned by
this course. It never clears unrelated RflySim entities.

The implementation first verifies a project-selected primitive wall/platform
asset using the installed RflySim examples. If the selected asset cannot be
observed by the configured LiDAR, loading fails with a diagnostic instead of
reporting the course as usable.

### Planning geometry

A ROS1 Python node reads the same JSON and publishes a deterministic
`sensor_msgs/PointCloud2` representation of the walls and platform sides. The
point spacing defaults to 0.10 m and the frame is `world`. The generated cloud
is a reference/global map for offline validation and planner testing; the live
FAST-LIO path continues to use each UAV's isolated RflySim LiDAR topics.

### CopterSim terrain

The generator creates a constant 16-bit flat height image and matching TXT
calibration under a project-owned generated-artifact directory. Deployment to
`CopterSim/external/map` is an explicit separate command because installed
toolchain directories remain read-only during ordinary generation.

Dynamic walls are not CopterSim terrain. Collision acceptance therefore uses
RflySim LiDAR visibility plus a project-side geometric clearance evaluator;
the design does not claim that wall contact is enforced by CopterSim terrain
queries.

### Preview and reports

Generation produces a top-down SVG preview and a machine-readable validation
report. The preview shows dimensions, centreline, wall footprint, takeoff
poses, landing platforms, frame axes, and safety-envelope clearance.

## Integration

The existing `/uav1` and `/uav2` namespaces, sensor isolation, MAVLink ports,
and Stage 7 arm gates remain unchanged. A project launcher loads the course
after RflySim3D is available and before any arm-capable flight runner starts.
The launcher records the course-spec checksum and refuses to use a stale
validation report from a different specification.

The takeoff coordinates become the map-specific defaults used by the generated
SITL wrapper. Existing Stage 5 event formats and mission interfaces are not
changed.

## Failure Handling

Generation and loading fail closed when:

- dimensions violate the guide limits;
- wall segments overlap either takeoff safety envelope;
- a landing platform is outside the landing zone or platform spacing is not
  greater than 1.5 m;
- object IDs collide or exceed the course-owned range;
- an asset or UE connection is unavailable;
- RflySim LiDAR does not observe the validation wall;
- generated artifacts do not match the course-spec checksum.

No failure path requests OFFBOARD mode or arms a vehicle.

## Testing and Acceptance

Implementation follows test-driven development. Offline tests verify schema
parsing, exact dimensions, guide constraints, centreline length, turn radii,
wall tessellation, collision-envelope clearance, platform spacing, deterministic
IDs, point-cloud sampling, flat terrain encoding, and checksum/staleness rules.

The map is accepted when:

1. generation is deterministic for the committed V1 specification;
2. the preview and validation report match the geometry in this document;
3. RflySim3D shows the takeoff area, complete S-passage, and two landing
   platforms without missing objects;
4. each isolated UAV LiDAR observes the nearby wall geometry;
5. both UAVs spawn on the flat takeoff area without overlap;
6. a no-arm topic probe confirms both sensor chains remain isolated;
7. existing offline validators remain green.

An armed corridor flight is not part of map acceptance. It remains a separate
explicit simulation-only run after no-arm validation succeeds.

## Deferred Scope

- coloured label, QR, and temperature-source task targets;
- ArUco texture generation and detection;
- boxes, supports, swinging pendulums, or other internal obstacles;
- randomized course variants;
- scoring and mission-action logic;
- a cooked UE4/UE5 native map;
- real-aircraft operation or automatic real-hardware arming.
