# Stage 7 Dual-Sensor Isolation Design

## Problem

The first armed Stage 7 run allowed both vehicles to take off, but their
estimated positions then diverged and the vehicles left the useful map area.
The archived run never received an ego-swarm position command, so the planner
was not the source of the initial motion.

Live inspection found two unsafe assumptions in the localization chain:

- only one `rflysim_sensor_bridge.py --copter-id 1` process was running;
- both FAST-LIO instances subscribed to the same `/rflysim/sensor0/mid360_lidar`
  and `/rflysim/imu` topics.

The RflySim point cloud contains `x`, `y`, `z`, and `seg` fields. The selected
faster_lio Ouster preprocessing path also expects fields including `intensity`
and per-point time `t`. PCL currently fills the missing fields with zero, so
motion compensation is unavailable. This explains why a stationary readiness
probe can pass while localization becomes unsafe after motion begins.

Stage 7 must not permit planning or arming until both vehicles have independent,
identified sensor sources and FAST-LIO-compatible point clouds.

## Scope

This change owns the project-local RflySim sensor bridges, point-cloud
adaptation, FAST-LIO launch wiring, readiness checks, tests, and live no-arm
validation. It does not modify `28com_sim`, RflySimSDK, CopterSim, PX4 Firmware,
or upstream faster_lio/ego-swarm sources.

An armed flight is explicitly outside the implementation acceptance test. A
later armed test requires a new explicit user request after all no-arm gates
pass.

## Architecture

### Independent raw sensor sources

Run one project-owned bridge process per vehicle. Each process has:

- a unique ROS node namespace;
- an explicit CopterSim ID;
- a dedicated RflySim configuration whose `TargetCopter` matches that ID;
- unique sensor SeqIDs and UDP receive ports;
- a latched identity/status topic reporting the configured CopterSim ID,
  sensor SeqID, receive port, and source topic names.

UAV1 and UAV2 must never subscribe to the same raw LiDAR or IMU topic. The
bridge configurations are project-owned generated/static assets; the reference
`28com_uav/sensor_pkg/Config.json` remains read-only.

### Point-cloud adaptation

A small project-local adapter converts each vehicle's raw RflySim
`sensor_msgs/PointCloud2` stream to a normalized FAST-LIO input topic. It:

- rejects non-finite coordinates and malformed row/point sizes;
- preserves `x`, `y`, and `z`;
- publishes deterministic `intensity`, `ring`, and `t` fields required by the
  selected faster_lio preprocessing path;
- derives ring and scan-relative time from the configured RflySim scan layout
  and scan period, rather than wall-clock callback timing;
- guarantees non-decreasing per-point time starting at zero and bounded by one
  scan period;
- publishes diagnostics describing accepted/rejected scan counts and observed
  time span.

The adapter parameters must match the RflySim sensor configuration. A layout or
point-count mismatch is a hard failure, not a best-effort conversion.

### FAST-LIO wiring

The dual FAST-LIO launch receives four explicit normalized inputs:

| Vehicle | LiDAR | IMU |
| --- | --- | --- |
| UAV1 | `/uav1/rflysim/lidar` | `/uav1/rflysim/imu` |
| UAV2 | `/uav2/rflysim/lidar` | `/uav2/rflysim/imu` |

Each FAST-LIO instance continues to publish only to its own SLAM and MAVROS
odometry namespace. Shared sensor defaults and the
`shared_rflysim_bridge` configuration mode are removed. Launching with equal
UAV1/UAV2 input topics is rejected before ROS processes start.

## Safety Gates

Readiness is fail-closed and separated into layers:

1. **Identity:** both bridge identity messages exist and report different
   CopterSim IDs, SeqIDs, ports, nodes, and raw LiDAR/IMU topics.
2. **Schema:** both normalized clouds contain the required fields, finite
   coordinates, valid dimensions, and a monotonic scan-relative time span.
3. **Freshness:** LiDAR, IMU, SLAM odometry, and MAVROS feedback advance for
   both vehicles without timestamp regressions.
4. **Isolation:** ROS publisher inspection shows that each normalized topic has
   exactly its expected project bridge/adapter publisher and that neither
   FAST-LIO instance consumes the other vehicle's topics.
5. **Stationary stability:** while disarmed on the ground, each estimator stays
   within configured position, velocity, attitude, and timestamp limits for a
   continuous observation window.
6. **No-arm motion qualification:** if an available simulator-only movement
   mechanism can move the vehicles without OFFBOARD/arming, localization must
   remain bounded during and after that motion. If such a mechanism is not
   available, the report records the check as unavailable rather than passing
   it.

Planner launch and every arm-capable runner require a saved, current-run report
showing gates 1 through 5 passed. The runner also rejects stale reports,
simulation-instance changes, bridge restarts, and any vehicle that is already
armed. Gate 6 is additional evidence and never weakens gates 1 through 5.

## Failure Handling

On any bridge, adapter, schema, freshness, isolation, or stability failure:

- do not launch ego-swarm or the setpoint bridge;
- do not publish OFFBOARD setpoints;
- do not call mode or arming services;
- write a run-scoped failure report containing the failed gate and observed
  values;
- leave both vehicles disarmed and in their existing manual mode.

If a failure occurs after a no-arm readiness run begins, monitoring terminates
the readiness run and invalidates its report. The design does not attempt an
automatic recovery that could conceal source reassignment or estimator resets.

## Testing

Implementation follows test-driven development.

Offline tests cover:

- rejection of shared LiDAR, IMU, SeqID, port, or CopterSim identity;
- config generation for CopterSim 1 and 2 without modifying reference files;
- point-cloud conversion with the exact RflySim `x/y/z/seg` schema;
- rejection of malformed, non-finite, incorrectly sized, or timestamp-regressing
  clouds;
- monotonic bounded `t` values and correct output field layout;
- fail-closed report parsing, stale-run rejection, and dry-run contracts.

Live no-arm validation then proves:

- two distinct bridge identities and publisher graphs;
- independent raw and normalized LiDAR/IMU streams;
- no missing-field warnings from faster_lio;
- two finite SLAM/MAVROS odometry streams;
- continuous stationary stability with both vehicles `armed: false`.

All existing Stage 0 through Stage 7 offline validators must remain green.

## Acceptance

The implementation is complete when:

- the project starts two independently identified RflySim sensor chains;
- each FAST-LIO instance consumes only its vehicle's normalized inputs;
- the cloud adapter produces validated scan-relative timing without upstream
  source changes;
- unsafe shared-input configurations fail before planner or arm-capable code can
  start;
- a saved live no-arm report passes identity, schema, freshness, isolation, and
  stationary-stability gates for both vehicles;
- both vehicles remain disarmed throughout acceptance validation.

This acceptance does not authorize another flight. Flight authorization remains
a separate explicit user decision based on the saved no-arm evidence.
