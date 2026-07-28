# Stage 6A Target Provider and Executor Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an ideal target provider and make the mission executor consume provider target results.

**Architecture:** The provider reads target config and writes deterministic target results offline, with an optional ROS `std_srvs/Trigger` service for live simulation. The executor accepts `--target-results` in dry-run and parses ROS Trigger JSON in live mode. Stage 6A validation covers provider output, executor target events, and Stage 5E regression.

**Tech Stack:** Python 3 standard library, optional ROS1 `rospy` and `std_srvs`, PowerShell validation, JSON/JSONL fixtures, existing Stage 5B/5E chain.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Stage 6A offline validation must not start RflySim, ROS, PX4, MAVROS, WSL GUI, or ego-swarm runtime.
- Use exactly `/uav1` and `/uav2`.
- Preserve Stage 5A `mission_events.jsonl` compatibility.
- Keep fixed-waypoint fallback available while ego-swarm live integration remains gated.
- The first target provider source mode is `ideal`.

---

### Task 1: Stage 6A Validation Harness

**Files:**
- Create: `scripts/validate_stage6a.ps1`
- Create directory: `tests/fixtures/stage6a`

**Interfaces:**
- Consumes: target provider CLI, mission executor CLI, Stage 5E regression.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage6a.ps1`.

- [ ] **Step 1: Write the failing validation**

Create `scripts/validate_stage6a.ps1` requiring:

```text
config/stage5_behavior_tree.json
config/stage5_live_mission.json
config/stage6_targets.json
future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
future_aircraft_ws/src/multi_uav_mission/scripts/target_provider.py
scripts/validate_stage5e.ps1
tests/fixtures/stage6a/expected_target_results.json
tests/fixtures/stage6a/expected_executor_trace.json
tests/fixtures/stage6a/expected_mission_events.jsonl
tests/fixtures/stage6a/expected_score_summary.json
```

Run the target provider with `--target-types color_label,qr_code,thermal_source`, compare target results, run the executor with `--target-results`, compare executor outputs, then run Stage 5E validation.

- [ ] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6a.ps1
```

Expected: FAIL because the target config, provider, and fixtures do not exist.

### Task 2: Ideal Target Provider

**Files:**
- Create: `config/stage6_targets.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/target_provider.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`
- Modify: `future_aircraft_ws/src/multi_uav_mission/package.xml`

**Interfaces:**
- Consumes: `load_config(path: Path) -> dict`, `build_results(config: dict, target_types: list[str]) -> dict`.
- Produces: `target_results.json` and optional ROS Trigger service.

- [ ] **Step 1: Add target config**

Create three ideal targets: `color_label_red`, `qr_code_gate`, and `thermal_source_1`, each with type, position, confidence, and assigned UAV.

- [ ] **Step 2: Implement provider CLI**

Implement target filtering and deterministic JSON output.

- [ ] **Step 3: Add ROS service mode**

Add `--backend ros --service /mission/target_provider/query`, serving `std_srvs/Trigger` with result JSON in `message`.

### Task 3: Executor Target Result Bridge

**Files:**
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py`

**Interfaces:**
- Consumes: `--target-results target_results.json`.
- Produces: `target_detected` events using target ids, types, positions, confidence, and UAV from provider output.

- [ ] **Step 1: Extend CLI**

Add `--target-results`.

- [ ] **Step 2: Add dry-run target result loading**

When `CollaborativeTargetWork` runs in dry-run and target results are supplied, emit target events from the file.

- [ ] **Step 3: Add ROS Trigger target service call**

When ROS backend calls the configured target provider service, parse JSON response and return targets to the executor.

### Task 4: Fixtures and Docs

**Files:**
- Create: `tests/fixtures/stage6a/expected_target_results.json`
- Create: `tests/fixtures/stage6a/expected_executor_trace.json`
- Create: `tests/fixtures/stage6a/expected_mission_events.jsonl`
- Create: `tests/fixtures/stage6a/expected_score_summary.json`
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: deterministic provider and executor outputs.
- Produces: documented Stage 6A validation and live provider command.

- [ ] **Step 1: Generate fixtures**

Run provider and executor once, then save stable outputs to `tests/fixtures/stage6a`.

- [ ] **Step 2: Validate**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6a.ps1
```

Expected: PASS.

## Self-Review

- Spec coverage: Covers provider config, provider CLI, ROS service mode, executor bridge, fixtures, docs, and Stage 5E regression.
- Placeholder scan: No TBD or TODO placeholders are present.
- Type consistency: Config fields, CLI flags, function names, and fixture names are consistent.
