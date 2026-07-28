# Stage 5C ROS Mission Executor Design

## Scope

Stage 5C turns the Stage 5B live mission boundary plan into an executable mission runner. It is intentionally aggressive: the runner is structured for real ROS/MAVROS execution now, while the default path remains offline-safe and fixture-verifiable.

This stage must not arm aircraft, start RflySim, start WSL, open GUI programs, or call MAVROS services during validation. Live service calls are allowed only when the operator explicitly selects the ROS backend and passes an arming safety flag.

## Architecture

Add a mission executor under the existing project-owned `multi_uav_mission` package:

```text
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
scripts/validate_stage5c.ps1
tests/fixtures/stage5c/expected_executor_trace.json
tests/fixtures/stage5c/expected_mission_events.jsonl
tests/fixtures/stage5c/expected_score_summary.json
```

The executor reads a Stage 5B `live_mission_plan.json`. It executes each ordered action through a backend abstraction:

- `dry-run`: default backend, no ROS imports, no network, no arming, deterministic outputs.
- `ros`: live backend skeleton using `rospy`, MAVROS services, and ROS publishers.

Both backends emit the same mission event surface so Stage 3 scoring and Stage 5A behavior-tree checks remain compatible.

## Interfaces

CLI:

```text
mission_executor.py --plan live_mission_plan.json --events mission_events.jsonl --trace executor_trace.json --score score_summary.json
mission_executor.py --plan live_mission_plan.json --backend ros --events mission_events.jsonl --trace executor_trace.json --score score_summary.json
mission_executor.py --plan live_mission_plan.json --backend ros --allow-arm --events mission_events.jsonl --trace executor_trace.json --score score_summary.json
```

Supported actions:

- `wait_for_topics`
- `publish_warmup_setpoints`
- `call_service`
- `publish_position_setpoint`
- `publish_planner_goal`
- `write_score_report`

Output files:

- `mission_events.jsonl`: JSON Lines with at least `time` and `event`.
- `executor_trace.json`: ordered execution trace with sequence, stage, action, status, and ROS boundary metadata.
- `score_summary.json`: produced through the same scoring rules as Stage 3/Stage 5A.

## Safety

The executor defaults to `--backend dry-run`.

In `--backend ros`, arming service calls are blocked unless `--allow-arm` is present. A blocked arming action must be recorded in the trace as `blocked_by_safety_gate` and in mission events as `arming_blocked`. Non-arming ROS actions may be represented by the live backend skeleton but must fail clearly if required ROS Python modules are unavailable.

## Error Handling

The executor exits non-zero when the plan is missing, malformed, contains duplicate or unordered sequences, references unsupported actions, omits required action fields, or requests live ROS execution without ROS dependencies.

Dry-run execution must still validate every action shape. This keeps fixture validation meaningful and catches broken Stage 5B plan generation before live testing.

## Testing

`scripts/validate_stage5c.ps1` runs offline. It generates a Stage 5B plan into a temp directory, runs `mission_executor.py --backend dry-run`, compares `mission_events.jsonl`, `executor_trace.json`, and `score_summary.json` to fixtures, then runs `scripts/validate_stage5b.ps1 -Quiet`.

The validator must not import ROS or call MAVROS.

## Live Gate

Before using `--backend ros --allow-arm`, Stage 2 live MAVROS topic and service availability must be manually confirmed for both `/uav1` and `/uav2`. The first live run should use `--backend ros` without `--allow-arm` to validate topic waits, publisher construction, and safety blocking before any arming attempt.
