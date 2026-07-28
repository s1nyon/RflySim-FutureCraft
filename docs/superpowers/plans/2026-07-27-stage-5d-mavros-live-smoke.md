# Stage 5D MAVROS Live Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only MAVROS smoke checker that proves the `/uav1` and `/uav2` live interfaces are reachable before any real ROS execution.

**Architecture:** The smoke checker consumes the Stage 5 live config, validates the namespace/interface contract, and emits a deterministic readiness report. Dry-run validates structure only; ROS mode waits for topics and services without calling them. The stage remains read-only and cannot arm or publish setpoints.

**Tech Stack:** Python 3 standard library for offline execution, optional ROS1 `rospy` for readiness checks, PowerShell validation, JSON fixtures, existing Stage 5 live config and Stage 5C executor chain.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Do not arm aircraft or publish setpoints from Stage 5D validation.
- Do not start RflySim, QGroundControl, CopterSim, or GUI windows from validation.
- Use exactly `/uav1` and `/uav2`.
- Preserve Stage 5A `mission_events.jsonl` compatibility.
- Keep fixed-waypoint fallback available while ego-swarm live integration remains gated.
- Default checker backend must be read-only.

---

### Task 1: Stage 5D Validation Harness

**Files:**
- Create: `scripts/validate_stage5d.ps1`
- Create directory: `tests/fixtures/stage5d`

**Interfaces:**
- Consumes: Stage 5 live config, planned smoke checker, Stage 5C regression.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1`.

- [ ] **Step 1: Write the failing validation**

Create `scripts/validate_stage5d.ps1` to require:

```text
config/stage5_live_mission.json
future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py
scripts/validate_stage5c.ps1
tests/fixtures/stage5d/expected_mavros_smoke_report.json
```

The script must run the smoke checker into `$env:TEMP\future_aircraft_stage5d\mavros_smoke_report.json`, compare it to the fixture, then run `scripts/validate_stage5c.ps1 -Quiet`.

- [ ] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
```

Expected: FAIL because the smoke checker and fixture do not exist.

### Task 2: MAVROS Smoke Checker

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `load_config(path: Path) -> dict`, `validate_config(config: dict) -> None`, `build_report(config: dict, backend: str) -> dict`.
- Produces: CLI that writes `mavros_smoke_report.json`.

- [ ] **Step 1: Write the minimal implementation for validation**

Implement functions:

```python
def load_config(path):
    return json.loads(path.read_text(encoding="utf-8"))

def validate_config(config):
    # require exactly uav1 and uav2 plus the MAVROS topic/service fields

def build_report(config, backend="dry-run"):
    # report readiness without side effects

def main(argv=None):
    # parse --live-config, --backend, --report
```

Dry-run must produce a deterministic report with both UAVs marked ready by contract shape only.

- [ ] **Step 2: Add CMake install entry**

Add `scripts/mavros_smoke_check.py` to `catkin_install_python(PROGRAMS ...)`.

- [ ] **Step 3: Run validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
```

Expected: FAIL until fixtures are created.

### Task 3: Fixtures and Documentation

**Files:**
- Create: `tests/fixtures/stage5d/expected_mavros_smoke_report.json`
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: generated smoke report.
- Produces: documented Stage 5D validation and the next live gate.

- [ ] **Step 1: Generate expected fixture**

Run the smoke checker once and write the byte-stable JSON fixture.

- [ ] **Step 2: Run Stage 5D validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
```

Expected: PASS.

- [ ] **Step 3: Update docs**

Document Stage 5D validation, smoke checker command, and the next no-arm `mission_executor.py --backend ros` smoke gate.

### Task 4: Full Offline Regression

**Files:**
- No new files.

**Interfaces:**
- Consumes: Stage 0-5D validators.
- Produces: final verification evidence.

- [ ] **Step 1: Run Stage 5D and upstream validators**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5b.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
```

Expected: all PASS.

## Self-Review

- Spec coverage: Covers the read-only smoke checker, validator, fixture, docs, CMake install, and regression path.
- Placeholder scan: No TBD or TODO placeholders are present.
- Type consistency: Function names, CLI flags, and output names are consistent across tasks.
