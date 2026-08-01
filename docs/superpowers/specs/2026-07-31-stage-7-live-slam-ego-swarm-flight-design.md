# Stage 7 Live SLAM and Ego-Swarm Flight Design

## Problem

The next project goal is not more offline behavior-tree or vision work.  The
live flight stack must first reproduce the 28comsim-style localization and
planning chain in this project:

```text
RflySim sensors -> faster_lio/FAST-LIO -> MAVROS external odometry -> ego-swarm -> MAVROS OFFBOARD control
```

OFFBOARD cannot be treated as an independent fixed-route precheck, because PX4
OFFBOARD position control depends on usable local/external localization.  A
minimal fixed setpoint runner without FAST-LIO would only prove topic/service
availability, not the flight condition needed for takeoff and landing.

## Decision

Move to a live-first integration track:

1. Bring up two UAVs with RflySim sensor streams and two independent
   FAST-LIO/faster_lio instances.
2. Feed each SLAM odometry output into its own MAVROS namespace as external
   odometry.
3. Replace the 28comsim single-UAV ego-planner launch shape with project-local
   ego-swarm wrappers for `/uav1` and `/uav2`.
4. Run a minimal live mission: both UAVs enter OFFBOARD, arm in simulation only,
   take off, fly a short planned path, and land.

Vision, target detection, and the behavior tree stay out of this track until the
SLAM/planner/control loop is proven.

## Reference Interfaces

28comsim's single-UAV live order is:

```text
sensor_pkg/main.py
roslaunch faster_lio mapping_mid360.launch rviz:=false
roslaunch ego_planner FS-J310_ego-planner.launch
roslaunch object_det detection.launch
roslaunch mission_pkg basic_test.launch
```

For this project, the relevant subset is sensor, SLAM, planner, and flight
control.  Detection and mission behavior-tree launch files are intentionally
excluded.

Known 28comsim FAST-LIO bindings:

- LiDAR input: `/rflysim/sensor0/mid360_lidar`
- IMU input: `/rflysim/imu`
- FAST-LIO odometry output remapped from `/Odometry` to `/mavros/odometry/out`
- Static TF includes `odom -> camera_init` and `map -> odom`

Known 28comsim planner/control bindings:

- ego-planner odometry argument defaults to `/mavros/local_position/odom`
- `traj_server` remaps `/position_cmd` to `planning/pos_cmd`
- mission code consumes `planning/pos_cmd` and MAVROS state/setpoint services

Project-local replacements must preserve `/uav1` and `/uav2` namespaces and must
not modify 28comsim.

## Target Runtime Shape

Each UAV gets isolated runtime bindings:

| Role | UAV 1 | UAV 2 |
| --- | --- | --- |
| MAVROS namespace | `/uav1` | `/uav2` |
| Sensor namespace | `/uav1/rflysim/...` or explicit remap from RflySim source | `/uav2/rflysim/...` or explicit remap from RflySim source |
| SLAM node namespace | `/uav1/slam` | `/uav2/slam` |
| SLAM odometry to FCU | `/uav1/mavros/odometry/out` | `/uav2/mavros/odometry/out` |
| Planner odometry input | project-selected SLAM odom topic | project-selected SLAM odom topic |
| Planner command output | `/uav1/planning/pos_cmd` | `/uav2/planning/pos_cmd` |
| MAVROS setpoint output | `/uav1/mavros/setpoint_raw/local` | `/uav2/mavros/setpoint_raw/local` |

The exact RflySim dual-sensor topic names must be verified live before final
launch wiring.  If RflySim only exposes un-namespaced sensor topics, the project
must add project-local remaps or wrapper launch files rather than changing
28comsim.

## Safety Boundary

- Work only in `future_aircraft_sim`; do not edit `28com_sim`.
- Simulation arming requires `--allow-arm --simulation-only` and the existing
  `simulation_arm_policy` gate.
- Do not run real-hardware arming paths.
- Keep Stage 6D as the no-arm readiness gate; Stage 7+ may run live simulation
  arming only when explicitly requested.

## Acceptance

The track is complete when a saved live report shows both UAVs:

- receive FAST-LIO-backed localization,
- enter OFFBOARD,
- arm in simulation only,
- climb to the target takeoff altitude,
- execute a short ego-swarm-produced flight segment,
- land or switch to AUTO.LAND successfully,
- record mission events and score output under `logs/`.
