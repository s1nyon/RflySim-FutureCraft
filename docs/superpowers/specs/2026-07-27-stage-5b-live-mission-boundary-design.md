# Stage 5B Live Mission Boundary Design

## Scope

Stage 5B bridges the Stage 5A offline behavior-tree contract toward live ROS execution. It defines the ROS/MAVROS boundary for each behavior-tree phase and provides an offline-verifiable generator for the ordered live mission plan.

This stage does not arm aircraft, open RflySim, start WSL, publish live ROS topics, or replace the original `28com_uav` mission package. It fixes the action/service/topic contract that the later live mission node must implement.

## Architecture

Add a Stage 5B config and generator under the existing project-owned `multi_uav_mission` package:

```text
config/stage5_live_mission.json
future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py
scripts/validate_stage5b.ps1
tests/fixtures/stage5b/expected_live_mission_plan.json
```

The generator reads `config/stage5_behavior_tree.json` and `config/stage5_live_mission.json`, validates that the live interfaces cover every Stage 5A phase, and writes an ordered JSON plan. The plan describes topic waits, MAVROS service calls, setpoint publication phases, planner goal dispatch, target-provider calls, landing commands, and mission-event publication.

## Interfaces

The live boundary uses the existing two-UAV namespace convention:

- state topic: `/uavX/mavros/state`
- odometry topic: `/uavX/mavros/local_position/odom`
- setpoint topic: `/uavX/mavros/setpoint_raw/local`
- mode service: `/uavX/mavros/set_mode`
- arming service: `/uavX/mavros/cmd/arming`
- landing command: `/uavX/mavros/set_mode` with `AUTO.LAND`
- planner goal topic: `/uavX/planner/goal`
- target provider service: `/mission/target_provider/query`
- mission event topic: `/mission/events`

## Error Handling

The generator exits non-zero when either config is missing or malformed, when UAV namespaces do not match Stage 5A, when a required phase binding is missing, when setpoint frequency is below 20 Hz, or when required topics/services are empty.

## Testing

`scripts/validate_stage5b.ps1` runs offline. It compares generated `live_mission_plan.json` to a fixture and re-runs `scripts/validate_stage5.ps1 -Quiet` to guarantee the Stage 5A event contract is still intact.

## Live Gate

The next implementation after Stage 5B can turn this plan into a ROS node. That node should execute the plan against live MAVROS and emit the same `mission_events.jsonl` surface used by Stage 5A and Stage 3 scoring.
