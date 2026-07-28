# Future Aircraft Sim Stage 5 Behavior Tree Offline Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the offline-verifiable Stage 5A behavior tree contract for the two-UAV futureAircraftSim mission.

**Architecture:** Keep Stage 5 independent of ROS, PX4, MAVROS, RflySim, and ego-swarm runtime. A deterministic Python runner reads a JSON mission-stage config, writes JSONL mission events using the Stage 3 scoring surface, and a PowerShell validation script compares events and score summaries to fixtures.

**Tech Stack:** Python 3 standard library, PowerShell validation, JSON config, JSONL fixtures, existing `score_summary.py`, ROS1 package layout.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Stage 5A does not require ROS, PX4, MAVROS, RflySim, WSL, a live GUI, or ego-swarm runtime output.
- Use exactly `/uav1` and `/uav2` for the current competition requirement.
- Preserve the fixed-waypoint fallback path while ego-swarm remains behind the live integration gate.
- Emit mission events in the JSONL style consumed by Stage 3 scoring.
- Keep live ROS behavior-tree bindings out of Stage 5A.

---

### Task 1: Stage 5 Validation Skeleton

**Files:**
- Create: `scripts/validate_stage5.ps1`
- Create: `tests/fixtures/stage5/expected_mission_events.jsonl`
- Create: `tests/fixtures/stage5/expected_score_summary.json`

**Interfaces:**
- Consumes: Stage 5 files listed in the design.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage5.ps1`.

- [x] **Step 1: Write the failing validation**

Create `scripts/validate_stage5.ps1` that checks for:

```text
config/stage5_behavior_tree.json
future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py
tests/fixtures/stage5/expected_mission_events.jsonl
tests/fixtures/stage5/expected_score_summary.json
future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py
scripts/validate_stage3.ps1
```

It must run:

```powershell
python future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py --config config/stage5_behavior_tree.json --output $env:TEMP\future_aircraft_stage5\mission_events.jsonl
python future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py --events $env:TEMP\future_aircraft_stage5\mission_events.jsonl --output $env:TEMP\future_aircraft_stage5\score_summary.json
```

Then compare generated mission events byte-for-byte against `tests/fixtures/stage5/expected_mission_events.jsonl`, compare generated score JSON structurally against `tests/fixtures/stage5/expected_score_summary.json`, and re-run `scripts/validate_stage3.ps1 -Quiet`.

- [x] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5.ps1
```

Expected: FAIL because the Stage 5 config, runner, and fixtures do not exist yet.

### Task 2: Behavior Tree Config and Runner

**Files:**
- Create: `config/stage5_behavior_tree.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `config/stage5_behavior_tree.json`.
- Produces: `load_config(path: Path) -> dict`, `validate_config(config: dict) -> None`, `build_events(config: dict) -> list[dict]`, and CLI output at `--output`.

- [x] **Step 1: Add Stage 5 config**

Create `config/stage5_behavior_tree.json` with `mission_name`, `mode: fixed_waypoint_fallback`, `uavs`, ordered `stages`, `failure_policy: abort_and_land`, and `event_output_contract`.

- [x] **Step 2: Implement runner**

Implement `behavior_tree_runner.py` with validation for missing required fields, exact two-UAV set, duplicate stage names, unknown stage names, non-positive timeouts, and unsupported modes.

The deterministic event sequence must include:

```text
mission_start
multi_takeoff_start
uav_stage_success for uav1 multi_takeoff
uav_stage_success for uav2 multi_takeoff
multi_takeoff_success
enter_corridor_start
enter_corridor_success
collaborative_navigate_start
min_uav_distance
collaborative_navigate_success
collaborative_target_work_start
target_detected for color_label
target_detected for qr_code
target_detected for thermal_source
collaborative_target_work_success
exit_corridor_start
exit_corridor_success
aruco_landing_start
uav_stage_success for uav1 aruco_landing
uav_stage_success for uav2 aruco_landing
aruco_landing_success
mission_report_start
mission_report_success
mission_end
```

- [x] **Step 3: Install runner in CMake**

Add `scripts/behavior_tree_runner.py` to `catkin_install_python(PROGRAMS ...)` in `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`.

### Task 3: Fixtures and Verification

**Files:**
- Create: `tests/fixtures/stage5/expected_mission_events.jsonl`
- Create: `tests/fixtures/stage5/expected_score_summary.json`

**Interfaces:**
- Consumes: deterministic events from `behavior_tree_runner.py`.
- Produces: fixture data used by `scripts/validate_stage5.ps1`.

- [x] **Step 1: Write expected event fixture**

Create byte-stable JSONL with sorted keys, one compact JSON object per line, and a trailing newline.

- [x] **Step 2: Write expected score fixture**

Create expected JSON summary:

```json
{
  "collision_count": 0,
  "duration_s": 52.0,
  "failure_reasons": [],
  "min_uav_distance_m": 0.85,
  "mission_end_time": 52.0,
  "mission_start_time": 0.0,
  "offboard_loss_count": 0,
  "success": true,
  "targets_detected_count": 3,
  "timeout_count": 0
}
```

- [x] **Step 3: Run Stage 5 validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5.ps1
```

Expected: PASS.

### Task 4: Documentation and Regression Validation

**Files:**
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: Stage 5 config, runner, fixtures, validation results.
- Produces: documented Stage 5 workflow and execution record.

- [x] **Step 1: Document Stage 5 commands**

Add README commands for:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5.ps1
python future_aircraft_ws/src/multi_uav_mission/scripts/behavior_tree_runner.py --config config/stage5_behavior_tree.json --output logs/stage5_dry_run/mission_events.jsonl
```

- [x] **Step 2: Add execution record**

Append `AGENT2READ.md` with Stage 5 files, validation results, and live ROS behavior-tree gate status.

- [ ] **Step 3: Run full offline validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage3.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5.ps1
```

Expected: all PASS.

## Self-Review

- Spec coverage: Covers Stage 5A config, deterministic runner, event output, Stage 3 scoring compatibility, validation fixtures, docs, and the live ROS gate boundary.
- Placeholder scan: No TBD, TODO, or unspecified error handling remains.
- Type consistency: Function names and output fields match the Stage 5 design and validation script.
