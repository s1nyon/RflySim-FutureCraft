# Future Aircraft Sim Stage 0-1 Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable scaffold for `future_aircraft_sim`: ROS workspace directories, repeatable launch-script wrappers, configuration files, logging directories, and a validation script for the Stage 0/1 MVP.

**Architecture:** Keep the first deliverable script-first and adapter-ready. Batch files live under `future_aircraft_sim/scripts`, shared settings live under `future_aircraft_sim/config`, logs go under `future_aircraft_sim/logs`, and the ROS workspace remains under `future_aircraft_sim/future_aircraft_ws` with an initially empty `src` prepared for later packages.

**Tech Stack:** Windows `.bat` orchestration, PowerShell validation, ROS1 Noetic workspace layout, PX4 SITL/MAVROS launch placeholders, Markdown documentation.

## Global Constraints

- Work inside `D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\future_aircraft_sim`.
- Do not copy or modify the original `28com_uav` real-aircraft project.
- Use `/uav1` and `/uav2` as the namespace convention from the start.
- Simulation may auto-arm; real-aircraft operation must not auto-arm.
- All scripts must fail with a clear message when required environment variables or paths are missing.
- Stage 0/1 does not implement `ego-swarm`, visual perception, or full behavior trees.

---

### Task 1: Stage 0 Directory and Configuration Contract

**Files:**
- Create: `config/env_template.bat`
- Create: `config/uavs.json`
- Create: `logs/.gitkeep`
- Create: `future_aircraft_ws/src/.gitkeep`
- Create: `scripts/validate_stage0.ps1`

**Interfaces:**
- Consumes: `future_aircraft_sim` project directory.
- Produces: stable config paths and validation command used by later tasks.

- [x] **Step 1: Write the failing validation script**

Create `scripts/validate_stage0.ps1` with checks for these required paths:

```powershell
$required = @(
  'config/env_template.bat',
  'config/uavs.json',
  'future_aircraft_ws/src',
  'logs',
  'scripts/start_single_uav.bat',
  'scripts/start_two_uav.bat',
  'scripts/start_mavros_uav1.bat',
  'scripts/start_mavros_uav2.bat',
  'scripts/start_mission.bat',
  'scripts/record_logs.bat',
  'scripts/kill_all.bat'
)
```

- [x] **Step 2: Run validation to verify it fails**

Run: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1`
Expected: FAIL because the scripts/config files do not exist yet.

- [x] **Step 3: Add the directory and config files**

Create `config/env_template.bat` defining documented placeholders:

```bat
set RFLYSIM_ROOT=D:\PX4PSP
set FUTURE_AIRCRAFT_SIM_DIR=%~dp0\..
set FUTURE_AIRCRAFT_WS=%FUTURE_AIRCRAFT_SIM_DIR%\future_aircraft_ws
set ROS_MASTER_URI=http://127.0.0.1:11311
set ROS_IP=127.0.0.1
```

Create `config/uavs.json` defining `uav1` and `uav2` with namespace, sysid, UDP ports, takeoff position, hover altitude, and safety distances.

- [x] **Step 4: Run validation again**

Run: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1`
Expected: still FAIL because launch wrapper scripts are not created yet.

### Task 2: Batch Script Skeletons

**Files:**
- Create: `scripts/start_single_uav.bat`
- Create: `scripts/start_two_uav.bat`
- Create: `scripts/start_mavros_uav1.bat`
- Create: `scripts/start_mavros_uav2.bat`
- Create: `scripts/start_mission.bat`
- Create: `scripts/record_logs.bat`
- Create: `scripts/kill_all.bat`

**Interfaces:**
- Consumes: `config/env_template.bat`, `config/uavs.json`.
- Produces: stable script names required by `agent2Read.md` Stage 0.

- [x] **Step 1: Write each `.bat` wrapper with clear failure behavior**

Each script starts with:

```bat
@echo off
setlocal
call "%~dp0..\config\env_template.bat"
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
```

- [x] **Step 2: Add dry-run behavior**

Each script supports `--dry-run` and prints the command it would run instead of launching ROS/PX4. This keeps Stage 0 verifiable on machines where ROS is not available.

- [x] **Step 3: Run validation**

Run: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1`
Expected: PASS for file existence and basic script contract.

### Task 3: Documentation Sync

**Files:**
- Modify: `agent2Read.md`
- Create: `README.md`

**Interfaces:**
- Consumes: files from Tasks 1 and 2.
- Produces: operator-facing instructions for Stage 0/1.

- [x] **Step 1: Add README commands**

Document these commands:

```powershell
cd D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\future_aircraft_sim
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
scripts\start_single_uav.bat --dry-run
scripts\start_two_uav.bat --dry-run
```

- [x] **Step 2: Sync `agent2Read.md`**

Add a new “执行记录” section noting that Stage 0 scaffold files and validation scripts were created.

- [x] **Step 3: Run final validation**

Run: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1`
Expected: PASS.

## Self-Review

- Spec coverage: Covers Stage 0 and the beginning of Stage 1 from `agent2Read.md`; does not cover `ego-swarm`, target recognition, or full behavior tree implementation.
- Placeholder scan: Plan contains concrete files, commands, and expected outcomes. The ROS launch commands remain dry-run placeholders until the real PX4/RflySim command lines are confirmed locally.
- Type consistency: Script names and config paths match the task book sections `6.7` and `7`.


