# C++ Competition Mission — Interface Contract (starting point)

Date: 2026-09-02
Workspace: `future_aircraft_ws/src/future_aircraft_mission/`
Status: **SCAFFOLD / DESIGN START — implementation is human-led**

This contract fixes the ROS/frame/state vocabulary the C++ mission will use.
Topics, services, and frames below come from the frozen simulation baseline and
must not be "improved" independently of the frozen infrastructure.

## Principle

```text
C++ Mission decides WHAT to do.
EGO decides HOW to locally navigate.
```

The mission layer publishes high-level planner goals and switches PX4 modes; it
does not implement local trajectory planning.

## UAV1 ROS surface (from frozen baseline)

| Purpose | Interface | Notes |
| --- | --- | --- |
| vehicle state | `/uav1/mavros/state` | `connected/armed/mode`; OFFBOARD acceptance gate |
| feedback odom | `/uav1/mavros/local_position/odom` | frame `map`; ENU numeric local coordinates |
| EGO goal | `/uav1/planning/goal` (`PoseStamped`) | header.frame_id `map`; ENU local coordinates |
| planner command | `/uav1/planning/pos_cmd` | position + velocity/acceleration (evidence recorder) |
| set mode | `/uav1/mavros/set_mode` | OFFBOARD / AUTO.LAND |
| arm | `/uav1/mavros/cmd/arming` | simulation gate only; real vehicle human-only |

Coordinate convention: EGO goal coordinates are the same ENU local frame used by
the verified V2 runner (spawn-origin, `uav1_camera_init` numeric frame). Do not
mix MAVROS odometry-in/out/local-position semantics (see
[`tf-frame-contract.md`](tf-frame-contract.md)).

## Proposed class skeleton

```text
MissionManager
     │
     ├── UavAgent UAV1
     └── UavAgent UAV2
              │
              ├── VehicleInterface   (state + mode/arm services)
              ├── EgoInterface       (goal + planner evidence)
              ├── PerceptionInterface(future)
              └── SafetyMonitor      (watchdog/geofence evidence, future)
```

`CorridorCoordinator` and `TaskAllocator` are later phases; do not build them in
the first milestone.

## First C++ capability (state machine)

```text
WAIT_READY → TAKEOFF → SEND_EGO_GOAL → WAIT_REACHED → AUTO.LAND → DISARM → FINISHED
```

`WAIT_READY` = MAVROS connected + not armed + mode != OFFBOARD + EGO topics alive.
`TAKEOFF` = OFFBOARD + arm + altitude setpoint (reuse verified executor semantics:
direct MAVROS setpoint source until EGO first command).
`WAIT_REACHED` = 3D Euclidean distance to goal <= terminal tolerance for the
verified settle duration.

## Human-led development policy

- User writes the competition behavior/state logic with AI as architecture
  guidance, API reminders, code review, bug diagnosis, test design, and small
  local assistance.
- AI does not default to rewriting the whole package.
- Vehicle/Ego interface headers below are a starting skeleton for review, not a
  complete implementation.
