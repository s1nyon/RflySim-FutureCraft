# Stage 5D MAVROS Live Smoke Design

## Scope

Stage 5D is the live-readiness gate after Stage 5C. It verifies that the Stage 5 live mission boundary is wired to real MAVROS topics and services for both UAV namespaces, but it never arms aircraft, never publishes setpoints, and never starts RflySim or GUI windows.

This stage exists to answer one question: can the mission stack see the live `/uav1` and `/uav2` interfaces before we attempt any real ROS execution?

## Architecture

Add a smoke checker under the existing `multi_uav_mission` package:

```text
future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py
scripts/validate_stage5d.ps1
tests/fixtures/stage5d/expected_mavros_smoke_report.json
```

The checker reads `config/stage5_live_mission.json`, validates the mission interface contract, and emits a deterministic smoke report. It supports:

- `dry-run`: validates the declared topics/services only
- `ros`: waits for state/odom topics and set_mode/arming services, then reports readiness

The ROS mode is read-only. No service calls, no arming, no planner commands, no setpoint publication.

## Interfaces

CLI:

```text
mavros_smoke_check.py --live-config config/stage5_live_mission.json --report mavros_smoke_report.json
mavros_smoke_check.py --live-config config/stage5_live_mission.json --backend ros --report mavros_smoke_report.json
```

Required live fields:

- `/uavX/mavros/state`
- `/uavX/mavros/local_position/odom`
- `/uavX/mavros/setpoint_raw/local`
- `/uavX/mavros/set_mode`
- `/uavX/mavros/cmd/arming`
- `/uavX/planner/goal`

Output:

- `mavros_smoke_report.json` with per-UAV readiness, topic/service presence, and backend status

## Error Handling

The checker exits non-zero when the live config is malformed, a required field is missing, the namespace set is not exactly `/uav1` and `/uav2`, or live ROS readiness checks time out.

## Testing

`scripts/validate_stage5d.ps1` runs offline. It compares the generated smoke report to a fixture and then re-runs Stage 5C validation to protect the executor chain.

The validator must not arm aircraft or publish setpoints.

## Live Gate

Stage 5D is the last step before any `mission_executor.py --backend ros` smoke run. When this stage passes, the next live check can execute the mission executor in `--backend ros` mode without `--allow-arm` to confirm the safety gate blocks arming.
