# Stage 7 Live SLAM and Ego-Swarm Flight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run two simulated UAVs through FAST-LIO localization, ego-swarm planning, OFFBOARD, simulation arming, flight, and landing without using the vision or behavior-tree track.

**Architecture:** Mirror the proven 28comsim live order, but implement all wrappers and configuration inside `future_aircraft_sim`.  Treat FAST-LIO localization as the prerequisite for OFFBOARD flight, then connect ego-swarm planner output to the existing MAVROS simulation-arm gate.

**Tech Stack:** Windows batch launchers, WSL Bash, ROS1 Noetic, RflySim sensor bridge, faster_lio/FAST-LIO, ego-planner-swarm, MAVROS, PX4 SITL, PowerShell validators, JSON live reports.

## Global Constraints

- Do not modify `28com_sim`, Firmware, CopterSim, RflySim3D, or upstream ego-swarm source.
- Keep `/uav1` and `/uav2` as the live control namespaces.
- Keep Rfly SIL ports separate from MAVROS FCU URLs.
- Keep `scripts/wsl/*.sh` LF-only.
- Simulation arming requires `--allow-arm --simulation-only` and `simulation_arm_policy.allow_arm=true`.
- Do not include object detection, target-provider logic, or behavior-tree mission flow in this stage.

---

### Task 1: Capture the 28comsim Live Interface Contract

**Files:**
- Create: `config/stage7_live_slam_ego_swarm.json`
- Create: `scripts/validate_stage7.ps1`
- Modify: `README.md`
- Modify: `.agents/AGENT2READ.md`

**Interfaces:**
- Consumes: 28comsim `sensor_pkg/main.py`, `faster_lio mapping_mid360.launch`, and `FS-J310_ego-planner.launch` reference behavior.
- Produces: a project-local JSON contract listing sensor, SLAM, planner, MAVROS, and output report topics for both UAVs.

- [ ] **Step 1: Write the contract fixture first.**

  Define two UAV entries with `/uav1` and `/uav2`, including:

  ```json
  {
    "slam_odom_to_fcu_topic": "/uav1/mavros/odometry/out",
    "planner_cmd_topic": "/uav1/planning/pos_cmd",
    "mavros_state_topic": "/uav1/mavros/state",
    "mavros_setpoint_topic": "/uav1/mavros/setpoint_raw/local"
  }
  ```

  Repeat for `uav2` with `/uav2`.

- [ ] **Step 2: Add `scripts/validate_stage7.ps1`.**

  The validator must require:

  - `config/stage7_live_slam_ego_swarm.json`
  - future Stage 7 launcher paths
  - both UAV namespaces
  - both `/uav*/mavros/odometry/out` external-odometry outputs
  - both `/uav*/planning/pos_cmd` planner command outputs
  - no references to `object_det`, `target_provider`, or behavior-tree launch files

- [ ] **Step 3: Run the intended red check.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
  ```

  Expected: FAIL until the Stage 7 launchers exist.

### Task 2: Add Dual FAST-LIO Live Wrappers

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch`
- Create: `scripts/wsl/stage7_live_fastlio_dual.sh`
- Create: `scripts/run_live_fastlio_dual.bat`
- Modify: `scripts/validate_stage7.ps1`

**Interfaces:**
- Consumes: RflySim sensor topics and `faster_lio mapping_mid360.launch` behavior from 28comsim.
- Produces: two namespaced FAST-LIO instances and two external odometry outputs to MAVROS.

- [ ] **Step 1: Add the dual FAST-LIO launch wrapper.**

  It must instantiate one group for `uav1` and one for `uav2`, remapping sensor inputs and `/Odometry` output so each UAV writes only to its own namespace.

- [ ] **Step 2: Add the WSL live runner.**

  The runner must source ROS Noetic, the 28comsim workspace, and this project workspace.  It must start only sensor/SLAM components and write logs under `logs/stage7_live/`.

- [ ] **Step 3: Add the Windows entrypoint.**

  `scripts\run_live_fastlio_dual.bat --dry-run` must print the live sequence without starting ROS.

- [ ] **Step 4: Update and run validation.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
  ```

  Expected: PASS for offline contract checks only.

### Task 3: Add Project-Local Ego-Swarm Dual Wrapper

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch`
- Create: `scripts/wsl/stage7_live_ego_swarm_dual.sh`
- Create: `scripts/run_live_ego_swarm_dual.bat`
- Modify: `config/stage7_live_slam_ego_swarm.json`
- Modify: `scripts/validate_stage7.ps1`

**Interfaces:**
- Consumes: built ego-swarm workspace and FAST-LIO odometry topics.
- Produces: `/uav1/planning/pos_cmd` and `/uav2/planning/pos_cmd` planner outputs.

- [ ] **Step 1: Mirror the 28comsim planner launch shape.**

  Keep the `odom_topic`, `cloud_topic`, map-size, velocity, acceleration, and `traj_server` concepts, but parameterize them per UAV namespace.

- [ ] **Step 2: Ensure ego-swarm is sourced, not copied.**

  The runner must use the already built ego-swarm workspace via environment/config path and must not edit the upstream source.

- [ ] **Step 3: Validate topic contracts offline.**

  The validator must reject un-namespaced planner command topics and reject any launch file that points back to 28comsim's mission launch.

### Task 4: Add Minimal Live Flight Runner

**Files:**
- Create: `scripts/wsl/stage7_live_slam_ego_swarm_flight.sh`
- Create: `scripts/run_live_slam_ego_swarm_flight.bat`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py`
- Modify: `scripts/validate_stage7.ps1`

**Interfaces:**
- Consumes: MAVROS state/services, FAST-LIO odometry, ego-swarm planner command topics.
- Produces: `logs/stage7_live/flight_report.json`, `mission_events.jsonl`, `executor_trace.json`, and `score_summary.json`.

- [ ] **Step 1: Write the smoke checker contract.**

  The checker must verify for each UAV:

  - MAVROS connected state is available.
  - FAST-LIO odometry is being published.
  - ego-swarm planner command topic is active.
  - `/uav*/mavros/set_mode` and `/uav*/mavros/cmd/arming` services exist.

- [ ] **Step 2: Gate simulation arming.**

  The live runner must require an explicit `--allow-arm --simulation-only` path before calling arming services.

- [ ] **Step 3: Run live flight only after smoke passes.**

  The flight sequence is takeoff, short planned segment, and landing.  It must write the saved report before any success claim.

### Task 5: Documentation and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `.agents/AGENT2READ.md`
- Modify: `docs/stage4_ego_swarm_status.md`

**Interfaces:**
- Consumes: Stage 7 validation and live reports.
- Produces: current operator runbook and agent handoff notes.

- [ ] **Step 1: Document the live-first order.**

  ```text
  start_two_uav -> run_live_fastlio_dual -> run_live_ego_swarm_dual -> run_live_slam_ego_swarm_flight
  ```

- [ ] **Step 2: Run offline validators.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
  ```

- [ ] **Step 3: Record live evidence only from saved logs.**

  Do not mark Stage 7 live complete unless `logs/stage7_live/flight_report.json`
  shows both UAVs completed OFFBOARD, simulation arming, flight, and landing.

## Self-Review

- Spec coverage: The plan covers dual FAST-LIO, ego-swarm replacement inside this project, and the requested live takeoff/flight/landing loop.
- Placeholder scan: no TBD/TODO placeholders remain.
- Scope check: vision, target detection, and behavior-tree mission logic are explicitly excluded from this track.
