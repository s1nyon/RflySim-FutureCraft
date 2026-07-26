# Stage 5 futureAircraftSim Behavior Tree Design

## Scope

Stage 5A adds an offline-verifiable behavior tree contract for the futureAircraftSim multi-UAV mission. It defines the mission stages, transition rules, fallback behavior, event output, and validation fixtures before binding the task tree to live ROS actions, MAVROS control, or ego-swarm runtime output.

This stage does not replace the original `28com_uav` `mission_pkg`, does not require a live ROS master, and does not require RflySim, PX4 SITL, MAVROS, or ego-swarm to be running. Live execution remains a later gate after the contract can be validated from deterministic inputs.

## Goals

Stage 5A must establish a repeatable mission-phase contract for two UAVs:

- `MultiTakeoff`
- `EnterCorridor`
- `CollaborativeNavigate`
- `CollaborativeTargetWork`
- `ExitCorridor`
- `ArucoLanding`
- `MissionReport`

The offline runner must emit mission events in the same JSONL style consumed by Stage 3 scoring, so task-tree behavior can be validated without flight hardware or simulation windows. The runner must also preserve a fixed-waypoint fallback path for cases where ego-swarm is unavailable or still behind the live integration gate.

## Architecture

Add Stage 5 project-owned artifacts under the existing `multi_uav_mission` package and top-level config/tests structure:

```text
config/stage5_behavior_tree.json
future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py
scripts/validate_stage5.ps1
tests/fixtures/stage5/expected_mission_events.jsonl
tests/fixtures/stage5/expected_score_summary.json
```

The behavior tree runner is a pure Python CLI. It reads `config/stage5_behavior_tree.json`, validates the stage sequence, simulates deterministic phase transitions, and writes `mission_events.jsonl` to a caller-provided output path. Stage 5 validation then runs the existing Stage 3 scorer against those events and compares the result to the Stage 5 fixture.

The design intentionally keeps the runner small. It is not a full behavior-tree engine yet; it is the contract checkpoint for the mission tree that later ROS action nodes must satisfy.

## Components

### Stage Configuration

`config/stage5_behavior_tree.json` defines:

- `mission_name`
- `mode`: initially `fixed_waypoint_fallback`
- `uavs`: exactly `/uav1` and `/uav2` for the current competition requirement
- `stages`: ordered stage definitions with `name`, `timeout_s`, `success_event`, and optional per-UAV goal metadata
- `failure_policy`: `abort_and_land` for load-bearing failures
- `event_output_contract`: JSONL fields required by Stage 3 scoring

The config must reject missing UAVs, duplicate stage names, unknown stage names, non-positive timeouts, and unsupported fallback modes.

### Behavior Tree Runner

`behavior_tree_runner.py` exposes:

```python
def load_config(path: Path) -> dict
def validate_config(config: dict) -> None
def build_events(config: dict) -> list[dict]
def main(argv=None) -> int
```

CLI:

```powershell
python future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py --config config/stage5_behavior_tree.json --output logs/stage5_dry_run/mission_events.jsonl
```

The generated events must include:

- `mission_start`
- `<stage>_start`
- per-UAV stage success events where useful
- `<stage>_success`
- `target_detected` synthetic events for the Stage 5 target-work contract
- `min_uav_distance`
- `mission_end`

Stage names in event payloads use lowercase snake_case to keep logs stable across Python, PowerShell, and future ROS nodes.

### Validation Script

`scripts/validate_stage5.ps1` must:

1. Verify required Stage 5 paths exist.
2. Run the behavior tree runner into a temp output directory.
3. Compare generated `mission_events.jsonl` to the expected fixture.
4. Run `score_summary.py` against generated events.
5. Compare generated `score_summary.json` to the expected Stage 5 summary.
6. Re-run Stage 3 validation to ensure scoring compatibility.

Validation must not require ROS, PX4, MAVROS, RflySim, WSL, or a live GUI.

## Data Flow

```text
config/stage5_behavior_tree.json
        |
        v
behavior_tree_runner.py
        |
        v
mission_events.jsonl
        |
        v
score_summary.py
        |
        v
score_summary.json
```

Later live ROS integration must preserve this event surface. The live behavior tree may replace deterministic simulated transitions with ROS action outcomes, but it should still emit equivalent phase events and failure reasons.

## Error Handling

The runner exits non-zero with concise `[ERROR] ...` output when:

- config JSON is malformed
- required fields are missing
- UAV list is empty or not exactly the supported two-UAV set
- stage sequence is missing a required stage or contains an unknown stage
- timeout values are invalid
- output path cannot be written

Runtime failure policy is represented in the config even though Stage 5A uses a successful fixture. The first policy is `abort_and_land`: if a later live stage reports a load-bearing failure, the mission emits failure events and transitions toward landing instead of continuing into target work.

## Testing

Stage 5 uses fixture-based verification:

- A failing validation is written first and observed before Stage 5 files exist.
- The config and runner are added minimally to satisfy the validation.
- The generated mission events are compared byte-for-byte against `tests/fixtures/stage5/expected_mission_events.jsonl`.
- The generated score summary is compared structurally against `tests/fixtures/stage5/expected_score_summary.json`.
- Stage 0-5 validation should pass before the stage is considered complete.

## Non-Goals

Stage 5A does not:

- implement live MAVROS OFFBOARD control
- compile or launch a ROS behavior-tree library
- modify the original `28com_uav` mission package
- require ego-swarm trajectory output
- perform real visual recognition
- create the Stage 6 target provider

## Live Gate

After Stage 5A passes offline validation, the next live gate is to map each deterministic stage transition to ROS action/service boundaries:

- `MultiTakeoff` -> per-UAV arm/offboard/takeoff action
- `EnterCorridor` / `ExitCorridor` -> fixed waypoint fallback or planner goal action
- `CollaborativeNavigate` -> ego-swarm goal dispatch and trajectory status
- `CollaborativeTargetWork` -> Stage 6 target provider result
- `ArucoLanding` -> landing action
- `MissionReport` -> final log and score generation

This mapping must reuse the Stage 5 event contract rather than introducing a second logging surface.

