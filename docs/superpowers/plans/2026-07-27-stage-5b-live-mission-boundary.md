# Future Aircraft Sim Stage 5B Live Mission Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline-verifiable live ROS/MAVROS boundary plan for executing the Stage 5 behavior tree.

**Architecture:** Keep Stage 5B as a contract generator, not a live flight runner. A Python CLI consumes Stage 5A behavior-tree config plus Stage 5B live interface config and emits ordered JSON actions that future ROS nodes must execute.

**Tech Stack:** Python 3 standard library, PowerShell validation, JSON fixtures, existing Stage 5A runner and Stage 3 scoring surface, ROS1/MAVROS interface naming.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Do not arm aircraft or start RflySim/WSL/GUI from Stage 5B validation.
- Use exactly `/uav1` and `/uav2`.
- Preserve Stage 5A `mission_events.jsonl` compatibility.
- Keep fixed-waypoint fallback available while ego-swarm live integration remains gated.
- Require setpoint publication frequency to be at least 20 Hz.

---

### Task 1: Stage 5B Validation Skeleton

**Files:**
- Create: `scripts/validate_stage5b.ps1`
- Create directory: `tests/fixtures/stage5b`

**Interfaces:**
- Consumes: expected Stage 5B paths and Stage 5A validation.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage5b.ps1`.

- [x] **Step 1: Write the failing validation**

Create `scripts/validate_stage5b.ps1` to require:

```text
config/stage5_behavior_tree.json
config/stage5_live_mission.json
future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py
scripts/validate_stage5.ps1
tests/fixtures/stage5b/expected_live_mission_plan.json
```

Run the generator to `$env:TEMP\future_aircraft_stage5b\live_mission_plan.json`, compare it structurally to the fixture, then run `scripts/validate_stage5.ps1 -Quiet`.

- [x] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5b.ps1
```

Expected: FAIL because Stage 5B config, generator, and fixture do not exist.

### Task 2: Live Mission Config and Generator

**Files:**
- Create: `config/stage5_live_mission.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `load_json(path: Path) -> dict`, Stage 5A config, Stage 5B config.
- Produces: `build_plan(behavior_config: dict, live_config: dict) -> dict`.

- [x] **Step 1: Add live interface config**

Create `config/stage5_live_mission.json` with `mission_mode`, `setpoint_rate_hz`, `event_topic`, `target_provider_service`, `uavs`, and `stage_bindings`.

- [x] **Step 2: Implement generator CLI**

Implement:

```python
def load_json(path: Path) -> dict
def validate_configs(behavior_config: dict, live_config: dict) -> None
def build_plan(behavior_config: dict, live_config: dict) -> dict
def main(argv=None) -> int
```

The generated plan must include actions for preflight waits, OFFBOARD takeoff, enter corridor setpoint, planner goal dispatch, target provider query, exit corridor setpoint, AUTO.LAND, and mission report scoring.

- [x] **Step 3: Add CMake install entry**

Add `scripts/live_mission_contract.py` to `catkin_install_python(PROGRAMS ...)`.

### Task 3: Fixture and Documentation

**Files:**
- Create: `tests/fixtures/stage5b/expected_live_mission_plan.json`
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: generated Stage 5B live mission plan.
- Produces: documented Stage 5B validation and next live gate.

- [x] **Step 1: Generate expected fixture**

Run the generator once and write the byte-stable expected JSON fixture.

- [x] **Step 2: Run Stage 5B validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5b.ps1
```

Expected: PASS.

- [x] **Step 3: Update docs**

Document Stage 5B in `README.md` and append an execution record to `AGENT2READ.md`.

### Task 4: Full Offline Regression

**Files:**
- No new files.

**Interfaces:**
- Consumes: Stage 0-5B validators.
- Produces: final verification evidence.

- [x] **Step 1: Run Stage 0-5B validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage3.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5b.ps1
```

Expected: all PASS.

## Self-Review

- Spec coverage: Covers live boundary config, generator, fixture, Stage 5A regression, docs, and the next live node gate.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: Function names, config fields, and fixture output fields match across tasks.
