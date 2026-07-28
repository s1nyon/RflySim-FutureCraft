# Stage 5E Simulation ARM Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the mission executor to call arming services in explicitly authorized simulation runs.

**Architecture:** Extend `mission_executor.py` with `--live-config` and `--simulation-only`, and add a `simulation_arm_policy` to Stage 5 live config. The executor records arming authorization events before backend arming actions. Offline validation uses dry-run mode to prove the event and trace contract.

**Tech Stack:** Python 3 standard library, optional ROS1 `rospy` in existing ROS backend, PowerShell validation, JSON/JSONL fixtures, existing Stage 5B/5C/5D chain.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Stage 5E offline validation must not start RflySim, ROS, PX4, MAVROS, WSL GUI, or ego-swarm runtime.
- Arming requires `--allow-arm`, `--simulation-only`, and `simulation_arm_policy.allow_arm: true`.
- Use exactly `/uav1` and `/uav2`.
- Preserve Stage 5A `mission_events.jsonl` compatibility.
- Keep fixed-waypoint fallback available while ego-swarm live integration remains gated.

---

### Task 1: Stage 5E Validation Harness

**Files:**
- Create: `scripts/validate_stage5e.ps1`
- Create directory: `tests/fixtures/stage5e`

**Interfaces:**
- Consumes: Stage 5B plan generator, Stage 5E executor CLI, Stage 5D regression.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage5e.ps1`.

- [ ] **Step 1: Write the failing validation**

Create `scripts/validate_stage5e.ps1` requiring:

```text
config/stage5_behavior_tree.json
config/stage5_live_mission.json
future_aircraft_ws/src/multi_uav_mission/scripts/live_mission_contract.py
future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py
scripts/validate_stage5d.ps1
tests/fixtures/stage5e/expected_executor_trace.json
tests/fixtures/stage5e/expected_mission_events.jsonl
tests/fixtures/stage5e/expected_score_summary.json
```

The script must generate `live_mission_plan.json`, run `mission_executor.py --backend dry-run --allow-arm --simulation-only --live-config config/stage5_live_mission.json`, compare outputs to fixtures, and run `scripts/validate_stage5d.ps1 -Quiet`.

- [ ] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5e.ps1
```

Expected: FAIL because Stage 5E fixtures are absent and executor does not yet support the new flags.

### Task 2: Simulation Arm Policy

**Files:**
- Modify: `config/stage5_live_mission.json`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/mission_executor.py`

**Interfaces:**
- Consumes: `load_live_config(path: Path | None) -> dict`, `arm_authorized(action: dict, allow_arm: bool, simulation_only: bool, live_config: dict | None) -> bool`.
- Produces: arming events `arming_requested`, `arming_allowed_by_simulation_gate`, and `arming_service_called`.

- [ ] **Step 1: Add config policy**

Add:

```json
"simulation_arm_policy": {
  "allow_arm": true,
  "mode": "simulation_only",
  "operator_ack": "simulation_stage5e"
}
```

- [ ] **Step 2: Extend executor CLI and gate**

Add `--live-config` and `--simulation-only`. Load live config when supplied. Allow arming only when `allow_arm`, `simulation_only`, and `simulation_arm_policy.allow_arm` are true.

- [ ] **Step 3: Add event output**

For allowed arming actions, emit `arming_requested`, `arming_allowed_by_simulation_gate`, and `arming_service_called`. For takeoff setpoint actions in `multi_takeoff`, emit `takeoff_setpoint_published`.

### Task 3: Fixtures and Docs

**Files:**
- Create: `tests/fixtures/stage5e/expected_executor_trace.json`
- Create: `tests/fixtures/stage5e/expected_mission_events.jsonl`
- Create: `tests/fixtures/stage5e/expected_score_summary.json`
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: deterministic Stage 5E dry-run outputs.
- Produces: documented Stage 5E validation and live simulation command.

- [ ] **Step 1: Generate fixtures**

Run generator and executor once with Stage 5E flags, then save stable outputs to `tests/fixtures/stage5e`.

- [ ] **Step 2: Validate**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5e.ps1
```

Expected: PASS.

- [ ] **Step 3: Update docs**

Document Stage 5E dry-run validation and live simulation arm command.

### Task 4: Full Regression

**Files:**
- No new files.

**Interfaces:**
- Consumes: Stage 0-5E validators.
- Produces: final verification evidence.

- [ ] **Step 1: Run validators**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage5e.ps1
```

Expected: all PASS.

## Self-Review

- Spec coverage: Covers config policy, executor CLI, allowed arming events, takeoff events, validator, fixture, docs, and regression path.
- Placeholder scan: No TBD or TODO placeholders are present.
- Type consistency: CLI flags, config keys, fixture names, and event names match the design.
