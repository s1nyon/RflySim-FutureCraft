# Future Aircraft Sim Stage 4 Ego-Swarm Minimal Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first testable ego-swarm integration checkpoint: official upstream source, adapter configuration, offline command generation, validation fixtures, and docs.

**Architecture:** Keep upstream ego-swarm in `external/ego-planner-swarm` and keep all project-specific adapter code in `future_aircraft_ws/src/multi_uav_mission`. Stage 4 validates integration contracts offline before attempting full ROS compilation or live planner execution.

**Tech Stack:** Python 3 standard library, PowerShell validation, Windows batch wrappers, JSON fixtures, ROS1 Noetic package layout, official `ZJU-FAST-Lab/ego-planner-swarm` repository.

## Global Constraints

- Do not modify the original `28com_uav` project.
- Do not modify the official `ego-planner-swarm` upstream source for Stage 4.
- Do not require ROS, PX4, MAVROS, RflySim, or a live WSL session for offline validation.
- Use `/uav1` and `/uav2` namespace contracts.
- Keep fixed-waypoint fallback available if ego-swarm cannot compile within the dependency gate.

---

### Task 1: Stage 4 Validation Skeleton

**Files:**
- Create: `scripts/validate_stage4.ps1`
- Create: `tests/fixtures/stage4/expected_ego_swarm_commands.json`

**Interfaces:**
- Consumes: expected Stage 4 files and fixture.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1`.

- [ ] **Step 1: Write failing validation**

Create `scripts/validate_stage4.ps1` that checks for these paths:

```text
config/stage4_ego_swarm.json
external/ego-planner-swarm
future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py
scripts/clone_ego_swarm.bat
tests/fixtures/stage4/expected_ego_swarm_commands.json
```

It must run the adapter CLI with:

```powershell
python future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py --config config/stage4_ego_swarm.json --output $env:TEMP\future_aircraft_stage4_ego_swarm_commands.json
```

It must compare the generated JSON fields `uav_id`, `namespace`, `odom_topic`, `goal_topic`, `trajectory_topic`, `frame_id`, and `launch_command` against the fixture.

- [ ] **Step 2: Run validation to verify it fails**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
```

Expected: FAIL because Stage 4 config and adapter do not exist yet.

### Task 2: Adapter Config and CLI

**Files:**
- Create: `config/stage4_ego_swarm.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py`
- Create: `tests/fixtures/stage4/expected_ego_swarm_commands.json`

**Interfaces:**
- Consumes: `config/stage4_ego_swarm.json`
- Produces: JSON object with `planner`, `source_dir`, `fallback_mode`, and `uavs` command entries.

- [ ] **Step 1: Write the expected fixture**

Create `tests/fixtures/stage4/expected_ego_swarm_commands.json` with two UAV entries using `/uav1` and `/uav2`.

- [ ] **Step 2: Implement adapter CLI**

Implement functions:

```python
def load_config(path: Path) -> dict
def build_commands(config: dict) -> dict
def main(argv=None) -> int
```

Required validation:

- `planner` must equal `ego-swarm`.
- `source_dir` must be non-empty.
- `uavs` must contain at least one UAV.
- Each UAV must define `uav_id`, `namespace`, `odom_topic`, `goal_topic`, and `trajectory_topic`.

The generated `launch_command` is:

```text
roslaunch ego_planner swarm.launch drone_id:=<index> odom_topic:=<odom_topic> goal_topic:=<goal_topic> trajectory_topic:=<trajectory_topic> frame_id:=<frame_id>
```

- [ ] **Step 3: Run adapter fixture verification**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
```

Expected: FAIL only if the upstream repository has not been cloned yet.

### Task 3: Official Repository Acquisition

**Files:**
- Create: `scripts/clone_ego_swarm.bat`
- Create directory or clone into: `external/ego-planner-swarm`

**Interfaces:**
- Consumes: network access to `https://github.com/ZJU-FAST-Lab/ego-planner-swarm.git`.
- Produces: local official source under `external/ego-planner-swarm`.

- [ ] **Step 1: Create clone wrapper**

Create `scripts/clone_ego_swarm.bat` with `--dry-run` support. It must clone only when `external/ego-planner-swarm` does not already exist.

- [ ] **Step 2: Run clone wrapper dry-run**

Run:

```bat
scripts\clone_ego_swarm.bat --dry-run
```

Expected: prints the official clone command.

- [ ] **Step 3: Clone official latest repository**

Run:

```bat
scripts\clone_ego_swarm.bat
```

Expected: `external/ego-planner-swarm` exists with upstream files.

### Task 4: Documentation and Regression Validation

**Files:**
- Modify: `README.md`
- Modify: `AGENT2READ.md`

**Interfaces:**
- Consumes: Stage 4 commands and validation results.
- Produces: documented Stage 4 workflow and execution record.

- [ ] **Step 1: Document Stage 4 commands**

Add README section for:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
scripts\clone_ego_swarm.bat --dry-run
scripts\clone_ego_swarm.bat
```

- [ ] **Step 2: Add execution record**

Append `AGENT2READ.md` with Stage 4 files, validation results, and live ROS gate status.

- [ ] **Step 3: Run full validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage3.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
```

Expected: all PASS.

## Self-Review

- Spec coverage: Covers official source acquisition, adapter contract, offline validation, docs, and fallback boundary.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: Adapter function names and JSON fields match validation and fixture expectations.
