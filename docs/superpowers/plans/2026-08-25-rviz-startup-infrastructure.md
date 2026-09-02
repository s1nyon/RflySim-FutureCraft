# RViz and Startup Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver optional truthful per-UAV RViz debugging and a measured, fail-closed reduction of fixed live-startup waits without changing PBL-1 flight behavior.

**Architecture:** A standalone ROS launch starts one or two RViz instances and per-UAV low-bandwidth visualization adapters; it is never included by the protected startup path. Startup work first measures the unchanged path, then replaces only the SITL/PX4/MAVROS waits that have functional predicates, retaining the scene delay unless live evidence proves a safe predicate.

**Tech Stack:** ROS Noetic XML launch/RViz, Python 3/rospy, Windows PowerShell 5.1, Bash in `RflySim-20.04`, existing lifecycle manifests/health JSON, focused synthetic Python checks.

## Global Constraints

- Keep `uav1_camera_init` and `uav2_camera_init` independent; do not create `competition_world`.
- RViz remains off by default and outside lifecycle health/readiness/control paths.
- Do not copy registered high-bandwidth clouds merely to change `frame_id`.
- Do not change ownership, manifest schema, stop semantics, launch order, mission, PX4, MAVROS, Faster-LIO, or EGO upstream.
- Every readiness timeout fails closed; preserve safe timeout ceilings while allowing early success.
- Use current branch `infra/tf-frame-live-probe`; do not push or merge.

---

### Task 1: Per-UAV visualization adapter and contract test

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/rviz_frame_adapter.py`
- Create: `tests/rviz_frame_adapter_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: per-UAV `nav_msgs/Odometry`, EGO `visualization_msgs/Marker` goal/optimal-list topics.
- Produces: bounded `nav_msgs/Path` and relabeled visualization-only Marker topics under `/uavX/viz/*`.

- [ ] **Step 1: Write failing pure-Python checks**

  Load the module without ROS installed by injecting message stubs. Assert `normalize_marker(marker, frame)` deep-copies the marker, changes only `header.frame_id`, and preserves stamp/points/pose. Assert `BoundedPath(max_poses=3)` preserves pose numeric values and keeps only the newest three samples.

- [ ] **Step 2: Run RED check**

  Run:

  ```powershell
  D:\PX4PSP\Python38\python.exe tests\rviz_frame_adapter_check.py --module future_aircraft_ws\src\multi_uav_mission\scripts\rviz_frame_adapter.py
  ```

  Expected: non-zero because the module/functions do not exist.

- [ ] **Step 3: Implement minimal adapter**

  Provide these pure interfaces:

  ```python
  def normalize_marker(message, frame_id): ...

  class BoundedPath:
      def __init__(self, frame_id, max_poses): ...
      def append_odometry(self, odometry): ...
  ```

  ROS `main()` reads private parameters for input/output topics, target frame, and `max_path_poses`; subscribers use queue size 10 and visualization publishers use queue size 2. It never publishes control topics or transforms.

- [ ] **Step 4: Run GREEN check and compile check**

  Run the focused command above and:

  ```powershell
  D:\PX4PSP\Python38\python.exe -m py_compile future_aircraft_ws\src\multi_uav_mission\scripts\rviz_frame_adapter.py
  ```

- [ ] **Step 5: Register script installation**

  Add `scripts/rviz_frame_adapter.py` to the existing `catkin_install_python(PROGRAMS ...)` list and rerun the focused check.

### Task 2: Standalone project RViz launch and configurations

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_rviz.launch`
- Create: `future_aircraft_ws/src/multi_uav_mission/rviz/future_aircraft_uav1.rviz`
- Create: `future_aircraft_ws/src/multi_uav_mission/rviz/future_aircraft_uav2.rviz`
- Create: `tests/rviz_project_contract_check.py`
- Modify: `docs/current/tf-frame-contract.md`

**Interfaces:**
- Consumes: Task 1 adapter and current `/uav1`, `/uav2` topic contracts.
- Produces: `rviz_mode:=uav1|uav2|dual` standalone debugging command.

- [ ] **Step 1: Write failing launch/config contract checks**

  Assert the launch has exactly the three allowed modes, launches distinct RViz nodes/configs, starts adapters only for selected UAVs, and contains no static TF publisher. Assert config fixed frames are `uav1_camera_init` and `uav2_camera_init`, and topics are namespace-correct. Assert protected Stage 7 launch remains `rviz:=false` and does not include the project RViz launch.

- [ ] **Step 2: Run RED check**

  ```powershell
  D:\PX4PSP\Python38\python.exe tests\rviz_project_contract_check.py --project-root .
  ```

  Expected: non-zero because the launch/configs do not exist.

- [ ] **Step 3: Add minimal launch and configurations**

  Each RViz config enables TF, Odometry, bounded adapter Path, adapted LiDAR, relabeled EGO optimal trajectory, and relabeled goal. Registered cloud, occupancy, and ground truth stay disabled/not configured because their truthful/performance contract is not verified. `dual` starts two independent RViz nodes.

- [ ] **Step 4: Run GREEN/static validation**

  Run the focused check, `xmllint --noout` in WSL for the launch, and package build for `multi_uav_mission`.

- [ ] **Step 5: Live validate on the first unchanged-startup timing stack**

  After READY, launch UAV1, UAV2, and dual modes in turn. Observe both fixed frames, LiDAR orientation, odometry/path direction, and EGO markers. Record RViz process isolation and a probe frequency comparison with RViz off/on.

- [ ] **Step 6: Commit Phase 2**

  ```powershell
  git commit -m "viz: add per-uav project rviz debugging"
  ```

### Task 3: Three unchanged-startup measurements and timing report

**Files:**
- Create: `scripts/lifecycle/startup_timing.py`
- Create: `tests/startup_timing_check.py`
- Create ignored artifacts: `logs/startup_timing/<run>/report.json`, `report.md`

**Interfaces:**
- Consumes: stack manifest, health JSON, `stage2_trace.log`, Stage 7 context/readiness report, and manifest entity timestamps.
- Produces: normalized stage records and a three-run aggregate table without changing startup behavior.

- [ ] **Step 1: Run three standard RViz-off fresh starts**

  For each run: doctor/status, start DryRun, start Execute, inspect ownership/health, wait for dev READY, record wall-clock command start/end, stop DryRun, stop Execute, verify clean ownership. Do not arm.

- [ ] **Step 2: Write failing synthetic timing checks**

  Test ISO timestamp parsing, ordered duration calculation, missing-stage `UNKNOWN`, immediate/delayed stage normalization, and mean/min/max aggregation.

- [ ] **Step 3: Run RED check**

  ```powershell
  D:\PX4PSP\Python38\python.exe tests\startup_timing_check.py --module scripts\lifecycle\startup_timing.py
  ```

- [ ] **Step 4: Implement report generator and run GREEN check**

  Expose:

  ```python
  def normalize_run(evidence): ...
  def summarize_runs(runs): ...
  def write_reports(run, json_path, markdown_path): ...
  ```

  Generate reports for all three retained run artifacts and identify the dominant fixed waits.

### Task 4: Replace predicate-backed fixed waits

**Files:**
- Create: `scripts/wsl/wait_px4_sockets.sh`
- Create: `tests/startup_readiness_gate_check.py`
- Modify: `scripts/start_two_uav.bat`
- Modify: `scripts/wsl/stage2_two_mavros.sh`
- Modify: `scripts/validate_stage2.ps1`
- Modify: `config/env_template.bat`

**Interfaces:**
- Consumes: PX4 Unix sockets, actual `px4-mavlink` command success, MAVROS connected messages.
- Produces: early progression on readiness and unchanged fail-closed timeout behavior.

- [ ] **Step 1: Write failing readiness/static checks**

  Verify immediate socket readiness exits without a sleep cycle, delayed readiness polls then succeeds, missing/invalid socket times out non-zero, and process existence alone cannot satisfy the gate. Static checks reject unconditional `STAGE2_BOOT_WAIT_SECONDS`, fixed sleeps between MAVROS launches, and unbounded loops.

- [ ] **Step 2: Run RED check**

  ```powershell
  D:\PX4PSP\Python38\python.exe tests\startup_readiness_gate_check.py --project-root .
  ```

- [ ] **Step 3: Implement the minimal gates**

  `wait_px4_sockets.sh` accepts `--timeout-seconds` and `--poll-seconds`, requires both `/tmp/px4-sock-1` and `/tmp/px4-sock-2` to be Unix sockets, logs elapsed time, and exits non-zero on timeout. `start_two_uav.bat` invokes it through the existing bounded WSL runner before MAVROS launch. `stage2_two_mavros.sh` retries the actual stream/boot command path instead of sleeping two seconds and launches both MAVROS instances without fixed 3/2-second staggering before its existing connected-state gate.

- [ ] **Step 4: Run GREEN checks and lifecycle validators**

  Run focused checks, `validate_stage2.ps1`, `validate_lifecycle.ps1`, `validate_stage7.ps1`, and `validate_stage8.ps1`.

- [ ] **Step 5: Keep scene wait explicit**

  Preserve `PREDICTED_COURSE_SCENE_WAIT_SECONDS=10` unless the three baseline runs expose a reliable acknowledgement before load. Document it as retained rather than calling it a readiness gate.

### Task 5: Post-change startup and flight validation

**Files:**
- Create ignored artifacts: three post-change startup reports and two flight run artifacts.
- Modify: `docs/current/live-startup-and-rviz.md`
- Modify: `.agents/AGENT2READ.md`

**Interfaces:**
- Consumes: Tasks 2–4 and existing lifecycle/flight runners.
- Produces: before/after statistics and infrastructure acceptance evidence.

- [ ] **Step 1: Run complete offline validation**

  Run focused tests, repository/docs checks, lifecycle, Stage 6c/6d, Stage 7/8, launch XML check, and `multi_uav_mission` catkin build.

- [ ] **Step 2: Run three fresh RViz-off startup validations**

  Require 3/3 READY and clean stop. Generate the same timing report schema and compute mean/min/max plus absolute/percentage reduction.

- [ ] **Step 3: Run two fresh full existing-route regressions**

  Each run requires current readiness, `--simulation-only`, `--allow-arm`, policy/run/instance match, dual OFFBOARD/arm/navigation, zero collision/offboard-loss/timeout, landing/disarm, and clean stop.

- [ ] **Step 4: Document current truth**

  Record RViz commands/modes/fixed frames/limitations, before/after timing, predicates, retained waits, and run IDs without claiming a shared global frame.

- [ ] **Step 5: Request independent review and fix all Critical/Important findings**

  Review the full diff against this plan and the user requirements before commit.

- [ ] **Step 6: Commit Phase 3**

  ```powershell
  git commit -m "lifecycle: replace fixed startup waits with readiness gates"
  ```

- [ ] **Step 7: Verify final state**

  Re-run focused/static/repository validations, confirm `git status` clean, `sim.ps1 status` reports no active stack, and do not push or merge.
