# Future Aircraft Sim Stage 1 Single-UAV Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Stage 0 scaffold into a configurable single-UAV launch chain that reuses `28com_sim` to start RflySim3D, QGroundControl, CopterSim, PX4 SITL, the RflySim ROS bridge, and a minimal `mission_pkg basic_test.launch` task.

**Architecture:** Keep original `28com_sim` files read-only. Windows batch wrappers in `future_aircraft_sim/scripts` call the existing `28com_SITL/UAVSITL.bat` and a project-local WSL script. The WSL script launches the existing `28com_uav/sensor_pkg/main.py` first, then starts `mission_pkg basic_test.launch`.

**Tech Stack:** Windows batch, PowerShell validation, WSL `RflySim-20.04`, RflySim paid/full installation, ROS1 Noetic, `mission_pkg basic_test.launch`.

## Global Constraints

- Do not modify `28com_sim` or `28com_uav` reference files.
- Stage 1 is single UAV only and uses `/mavros/...` topics from the original single-aircraft stack.
- `start_single_uav.bat --dry-run` must work without launching GUI programs.
- Non-dry-run may launch RflySim3D, QGroundControl, CopterSim, PX4 SITL, VcXsrv, WSL, and xterm windows.
- The user has a paid RflySim installation with dongle inserted.

---

### Task 1: Stage 1 Validation

**Files:**
- Create: `scripts/validate_stage1.ps1`

**Interfaces:**
- Consumes: Stage 0 files and the Stage 1 script contract.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1`.

- [x] **Step 1: Write the failing validation script**
- [x] **Step 2: Run it and confirm it fails before Stage 1 files exist**

### Task 2: Stage 1 Config and Launch Wrappers

**Files:**
- Modify: `config/env_template.bat`
- Create: `config/stage1_single_uav.json`
- Create: `scripts/start_vcxsrv.bat`
- Create: `scripts/start_rflysim_sitl_single.bat`
- Create: `scripts/start_wsl_ros_single.bat`
- Modify: `scripts/start_single_uav.bat`
- Create: `scripts/wsl/stage1_single_uav.sh`

**Interfaces:**
- Consumes: `28com_sim/28com_SITL/UAVSITL.bat`, `28com_sim/UAV_demo/28com_uav/sensor_pkg/main.py`, `mission_pkg/launch/basic_test.launch`.
- Produces: single command `scripts\start_single_uav.bat` with `--dry-run` and real launch modes.

- [x] **Step 1: Add config variables for PSP, WSL distro, reference paths, and boot wait**
- [x] **Step 2: Add Windows-side SITL, VcXsrv, and WSL ROS wrappers**
- [x] **Step 3: Add WSL-side single-UAV ROS script**
- [x] **Step 4: Update `start_single_uav.bat` to orchestrate Stage 1**

### Task 3: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `agent2Read.md`

**Interfaces:**
- Consumes: Stage 1 wrappers.
- Produces: documented operator commands and task-book execution record.

- [x] **Step 1: Document Stage 1 dry-run and real launch commands**
- [x] **Step 2: Add Stage 1 execution record to `agent2Read.md`**
- [x] **Step 3: Run Stage 0 and Stage 1 validation**

## Self-Review

- Spec coverage: Covers Stage 1 launch orchestration and keeps Stage 2 multi-UAV work out of scope.
- Placeholder scan: Real launch mode calls the existing 28com SITL script and a concrete WSL script; no generic placeholder commands remain in the Stage 1 path.
- Risk note: The real launch path opens GUI and WSL processes. It is validated by dry-run here; live SITL validation requires operator observation of RflySim/QGC windows.
