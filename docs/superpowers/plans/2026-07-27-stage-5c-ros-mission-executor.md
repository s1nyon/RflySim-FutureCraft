# Stage 5C ROS Mission Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a ROS-shaped mission executor that can run the Stage 5B mission plan in deterministic dry-run mode and expose a guarded live ROS backend.

**Architecture:** The executor consumes `live_mission_plan.json`, validates action order and shape, runs each action through a backend, and writes `mission_events.jsonl`, `executor_trace.json`, and `score_summary.json`. Dry-run is the default and is used by validation; ROS mode is explicitly selected and arming is blocked unless `--allow-arm` is provided.

**Tech Stack:** Python 3 standard library for offline execution, optional ROS1 `rospy`/MAVROS imports for live mode, PowerShell validation, JSON/JSONL fixtures, existing Stage 5B plan generator and Stage 3 scoring code.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Do not arm aircraft or start RflySim/WSL/GUI from Stage 5C validation.
- Use exactly `/uav1` and `/uav2`.
- Preserve Stage 5A `mission_events.jsonl` compatibility.
- Keep fixed-waypoint fallback available while ego-swarm live integration remains gated.
- Require setpoint publication frequency to be at least 20 Hz.
- Default executor backend must be `dry-run`.
- ROS backend arming service calls require explicit `--allow-arm`.

---

### Task 1: Stage 5C Validation Harness

**Files:**
- Create: `scripts/validate_stage5c.ps1`
- Create directory: `tests/fixtures/stage5c`

**Interfaces:**
- Consumes: Stage 5B config, Stage 5B generator, planned `mission_executor.py`.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage5c.ps1`.

- [ ] **Step 1: Write the failing validation**

Create `scripts/validate_stage5c.ps1` to require:

```text
config/stage5_behavior_tree.json
config/stage5_live_mission.json
future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
future_aircraft_ws/src/multi_uav_mission/scripts/score_summary.py
scripts/validate_stage5b.ps1
tests/fixtures/stage5c/expected_executor_trace.json
tests/fixtures/stage5c/expected_mission_events.jsonl
tests/fixtures/stage5c/expected_score_summary.json
```

The script must generate `$env:TEMP\future_aircraft_stage5c\live_mission_plan.json`, run `mission_executor.py --backend dry-run`, compare outputs to fixtures, then run `scripts/validate_stage5b.ps1 -Quiet`.

- [ ] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5c.ps1
```

Expected: FAIL because `mission_executor.py` and fixtures do not exist.

### Task 2: Mission Executor Core

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `load_plan(path: Path) -> dict`, `execute_plan(plan: dict, backend: MissionBackend, allow_arm: bool) -> tuple[list[dict], list[dict]]`.
- Produces: CLI that writes events, trace, and score summary.

- [ ] **Step 1: Write the minimal implementation for validation**

Implement functions:

```python
def load_plan(path):
    return json.loads(path.read_text(encoding="utf-8"))

def validate_plan(plan):
    # validate mission_name, actions list, contiguous sequence numbers, supported action names

def execute_plan(plan, backend, allow_arm=False):
    # return events, trace

def main(argv=None):
    # parse --plan, --backend, --allow-arm, --events, --trace, --score
```

Dry-run must produce deterministic Stage 5A-compatible events and a trace entry for every Stage 5B action.

- [ ] **Step 2: Add CMake install entry**

Add `scripts/mission_executor.py` to `catkin_install_python(PROGRAMS ...)`.

- [ ] **Step 3: Run validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5c.ps1
```

Expected: FAIL because fixtures have not been generated yet, or PASS after fixtures exist.

### Task 3: Fixtures and Documentation

**Files:**
- Create: `tests/fixtures/stage5c/expected_executor_trace.json`
- Create: `tests/fixtures/stage5c/expected_mission_events.jsonl`
- Create: `tests/fixtures/stage5c/expected_score_summary.json`
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: deterministic dry-run executor outputs.
- Produces: documented Stage 5C validation and live safety gate.

- [ ] **Step 1: Generate expected fixtures**

Run `live_mission_contract.py`, then run `mission_executor.py --backend dry-run` and copy stable outputs into `tests/fixtures/stage5c`.

- [ ] **Step 2: Run Stage 5C validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5c.ps1
```

Expected: PASS.

- [ ] **Step 3: Update docs**

Document Stage 5C validation, dry-run executor command, ROS backend safety behavior, and append an execution record to `AGENT2READ.md`.

### Task 4: Full Offline Regression

**Files:**
- No new files.

**Interfaces:**
- Consumes: Stage 0-5C validators.
- Produces: final verification evidence.

- [ ] **Step 1: Run Stage 5C and upstream validators**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5b.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5c.ps1
```

Expected: both PASS.

## Self-Review

- Spec coverage: The plan covers executor CLI, dry-run backend, guarded ROS backend, events, trace, scoring, docs, CMake install, and regression validation.
- Placeholder scan: No TBD or TODO placeholders are present.
- Type consistency: Function names, paths, output names, and CLI flags match the design.
