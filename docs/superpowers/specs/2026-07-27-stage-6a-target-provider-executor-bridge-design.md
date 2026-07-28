# Stage 6A Target Provider and Executor Bridge Design

## Scope

Stage 6A adds the first target provider for the futureAircraftSim mission. It uses ideal target data so the mission can close the `CollaborativeTargetWork` loop before simulation vision is stable.

This stage also includes the Stage 5F bridge: the mission executor can consume target provider results and emit `target_detected` events from real provider output instead of only synthesizing target types from the plan.

## Architecture

Add an ideal target config and provider script:

```text
config/stage6_targets.json
future_aircraft_ws/src/multi_uav_mission/scripts/target_provider.py
scripts/validate_stage6a.ps1
tests/fixtures/stage6a/
```

The provider supports two modes:

- CLI dry-run: writes `target_results.json`
- ROS service: serves `/mission/target_provider/query` as `std_srvs/Trigger`, returning JSON in `response.message`

The executor gains `--target-results`. In dry-run validation, this file is used to produce `target_detected` events with real target ids, types, positions, confidence, and assigned UAVs. In ROS mode, the executor calls the target provider service and parses the JSON response.

## Interfaces

Target provider CLI:

```text
target_provider.py --config config/stage6_targets.json --target-types color_label,qr_code,thermal_source --output target_results.json
target_provider.py --config config/stage6_targets.json --backend ros --service /mission/target_provider/query
```

Executor CLI addition:

```text
mission_executor.py --target-results target_results.json
```

Target result schema:

```json
{
  "source_mode": "ideal",
  "frame_id": "map",
  "targets": [
    {
      "target_id": "color_label_red",
      "target_type": "color_label",
      "position": {"x": 3.2, "y": -0.45, "z": 1.0},
      "confidence": 1.0,
      "uav": "uav1"
    }
  ]
}
```

## Error Handling

The provider exits non-zero when target config is malformed, target ids are duplicated, required fields are missing, confidence is outside `[0, 1]`, or requested target types are absent.

The executor exits non-zero when `--target-results` is malformed or when a ROS target provider returns invalid JSON.

## Testing

`scripts/validate_stage6a.ps1` runs offline. It generates `target_results.json`, compares it to a fixture, generates a Stage 5B plan, runs the Stage 5E simulation-arm executor with `--target-results`, compares events, trace, and score fixtures, then re-runs Stage 5E validation.

The validator must not start ROS, RflySim, PX4, MAVROS, WSL GUI, or ego-swarm runtime.

## Live Gate

After Stage 6A, a live simulation run can start the target provider ROS service before `mission_executor.py --backend ros --allow-arm --simulation-only`. This gives `CollaborativeTargetWork` a concrete service endpoint.
