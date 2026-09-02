# Future Aircraft Sim Stage 2 Two-UAV Namespace Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add launch/config groundwork for two PX4 SITL vehicles and two MAVROS instances under `/uav1` and `/uav2` namespaces.

**Architecture:** Keep `28com_sim` read-only. Generate a temporary two-UAV SITL script from the original `28com_SITL/UAVSITL.bat` at runtime, replacing only position/yaw values. Launch MAVROS in WSL with `ROS_NAMESPACE=uav1` and `ROS_NAMESPACE=uav2` using separate fcu/gcs URLs and target system IDs.

**Tech Stack:** Windows batch, PowerShell validation, WSL `RflySim-20.04`, ROS1 Noetic, MAVROS `px4.launch`, RflySim/CopterSim/PX4 SITL.

## Global Constraints

- Do not modify original `28com_sim` or `28com_uav` files.
- Use `/uav1/mavros/...` and `/uav2/mavros/...` for Stage 2 ROS topics.
- Stage 2 does not implement multi-UAV mission logic or ego-swarm.
- Dry-run validation must not open RflySim, QGC, CopterSim, WSL, or xterm windows.

---

### Task 1: Stage 2 Validation

**Files:**
- Create: `scripts/validate_stage2.ps1`

**Interfaces:**
- Consumes: Stage 2 config and script contract.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1`.

- [x] **Step 1: Write the failing validation script**
- [x] **Step 2: Run it and confirm it fails before Stage 2 files exist**

### Task 2: Two-UAV Config and SITL Wrapper

**Files:**
- Modify: `config/env_template.bat`
- Create: `config/stage2_two_uav.json`
- Create: `scripts/start_rflysim_sitl_two.bat`
- Modify: `scripts/start_two_uav.bat`

**Interfaces:**
- Consumes: original `28com_sim/28com_SITL/UAVSITL.bat`.
- Produces: generated temporary two-UAV SITL script at runtime.

- [x] **Step 1: Add Stage 2 position/yaw and wait-time env variables**
- [x] **Step 2: Add config for `/uav1` and `/uav2` sysid/ports/positions**
- [x] **Step 3: Implement runtime generation of the two-UAV SITL script**

### Task 3: Two MAVROS Namespace Launch

**Files:**
- Create: `scripts/start_wsl_mavros_two.bat`
- Create: `scripts/wsl/stage2_two_mavros.sh`
- Modify: `scripts/start_mavros_uav1.bat`
- Modify: `scripts/start_mavros_uav2.bat`

**Interfaces:**
- Consumes: MAVROS `px4.launch` inside WSL/ROS.
- Produces: `/uav1/mavros/state`, `/uav2/mavros/state`, `/uav1/mavros/local_position/odom`, `/uav2/mavros/local_position/odom` when live launch succeeds.

- [x] **Step 1: Add WSL script that starts both MAVROS instances in namespaces**
- [x] **Step 2: Update per-UAV MAVROS wrappers for dry-run and real WSL launch**
- [x] **Step 3: Update `start_two_uav.bat` to orchestrate VcXsrv, two-UAV SITL, and two MAVROS**

### Task 4: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `agent2Read.md`

**Interfaces:**
- Consumes: Stage 2 scripts.
- Produces: documented Stage 2 commands and execution record.

- [x] **Step 1: Document Stage 2 dry-run and real launch commands**
- [x] **Step 2: Add task-book execution record**
- [x] **Step 3: Run Stage 0, Stage 1, and Stage 2 validation**

## Self-Review

- Spec coverage: Covers Stage 2 launch and namespace foundation, not mission_pkg multi-UAV refactor.
- Placeholder scan: Real Stage 2 launch has concrete commands for SITL and MAVROS; mission logic remains explicitly out of scope.
- Risk note: Live validation still requires observing QGC/RflySim/ROS windows and checking MAVROS topic availability.
