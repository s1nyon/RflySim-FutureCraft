# Stage 6D ODOMETRY Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the no-arm live smoke gate consume PX4's real MAVLink `ODOMETRY` data through MAVROS rather than waiting for the unavailable `LOCAL_POSITION_NED_COV` path.

**Architecture:** Each dedicated PX4-to-MAVROS link continues to request `LOCAL_POSITION_NED` for `local_position/pose` and additionally requests `ODOMETRY`.  The Stage 5 live contract consumes the MAVROS extras output at `/uav*/mavros/odometry/in`; `odometry/out` is the reverse FCU input.  Offline contract checks make the stream request and topic names regressible; a fresh GUI restart and a read-only Stage 6D run provide the only live acceptance evidence.

**Tech Stack:** Bash/WSL launch scripts, PX4 `px4-mavlink`, MAVROS Noetic extras, Python 3 smoke checker, PowerShell contract validators, JSON fixtures.

## Global Constraints

- Do not modify `28com_sim`, Firmware, CopterSim, or RflySim3D.
- Preserve the `/uav1` and `/uav2` namespaces and the dedicated FCU URLs `udp://:14601@127.0.0.1:14600` and `udp://:14611@127.0.0.1:14610`.
- Do not use the Rfly SIL/CopterSim ports `16540/17540` or `16541/17541` for MAVROS.
- Keep `scripts/wsl/*.sh` LF-only.
- Stage 6D validation must not arm, set mode, or publish FCU setpoints.
- Do not claim live success without a fresh GUI restart and a saved, passing Stage 6D live report.
- Update `.agents/AGENT2READ.md` and `README.md` because this changes the project live interface contract.

---

### Task 1: Add the failing offline odometry-path contract

**Files:**
- Modify: `scripts/validate_stage2.ps1`
- Modify: `scripts/validate_stage5d.ps1`
- Modify: `scripts/validate_stage6d.ps1`

**Interfaces:**
- Consumes: `scripts/wsl/stage2_two_mavros.sh` and `config/stage5_live_mission.json`.
- Produces: validators that require two `ODOMETRY` requests and exactly `/uav1/mavros/odometry/in` plus `/uav2/mavros/odometry/in` as the live odom bindings.

- [ ] **Step 1: Require the two PX4 stream commands in the Stage 2 validator.**

  Add these literals to the existing `$wslText` contract list in `validate_stage2.ps1`:

  ```powershell
  '"$PX4_MAVLINK_BIN" --instance "$sysid" stream -u "$px4_port" -s ODOMETRY -r 30'
  ```

  Require the single parameterized command once because `start_px4_mavros_link` is called for both UAVs.

- [ ] **Step 2: Require the new live odom contract in Stage 5D and Stage 6D.**

  After loading `config/stage5_live_mission.json`, assert:

  ```powershell
  $expectedOdomTopics = @{
      uav1 = '/uav1/mavros/odometry/in'
      uav2 = '/uav2/mavros/odometry/in'
  }
  foreach ($uav in $config.uavs) {
      if ($uav.odom_topic -ne $expectedOdomTopics[$uav.uav_id]) {
          $contractErrors += "unexpected odom_topic for $($uav.uav_id): $($uav.odom_topic)"
      }
  }
  ```

  In Stage 5D, run the assertion before the dry-run report is created.  In Stage 6D, run it before the dry-run launcher checks.

- [ ] **Step 3: Run the intended red checks.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
  ```

  Expected: Stage 2 fails because the WSL script lacks the `ODOMETRY` stream request; Stage 5D and Stage 6D fail because the config still names `local_position/odom`.

- [ ] **Step 4: Commit the red contract.**

  ```powershell
  git add scripts/validate_stage2.ps1 scripts/validate_stage5d.ps1 scripts/validate_stage6d.ps1
  git commit -m "test: require MAVLink odometry smoke path"
  ```

### Task 2: Route real PX4 ODOMETRY into the Stage 6D contract

**Files:**
- Modify: `scripts/wsl/stage2_two_mavros.sh`
- Modify: `config/stage5_live_mission.json`
- Modify: `tests/fixtures/stage5d/expected_mavros_smoke_report.json`

**Interfaces:**
- Consumes: PX4 stream name `ODOMETRY`, each dedicated local PX4 port, and the existing MAVROS extras `OdometryPlugin`.
- Produces: `/uav1/mavros/odometry/in` and `/uav2/mavros/odometry/in` as the `odom_topic` values that `mavros_smoke_check.py` waits for.

- [ ] **Step 1: Add the minimal PX4 ODOMETRY request.**

  Directly after the existing `LOCAL_POSITION_NED` command in `start_px4_mavros_link()`, add:

  ```bash
  "$PX4_MAVLINK_BIN" --instance "$sysid" stream -u "$px4_port" -s ODOMETRY -r 30
  ```

  Do not alter the `start`, `boot_complete`, port values, FCU URLs, or stream rates already present.

- [ ] **Step 2: Change only the two declared odom inputs.**

  In `config/stage5_live_mission.json`, replace:

  ```json
  "/uav1/mavros/local_position/odom"
  "/uav2/mavros/local_position/odom"
  ```

  with:

  ```json
  "/uav1/mavros/odometry/in"
  "/uav2/mavros/odometry/in"
  ```

  Keep all state, service, setpoint, policy, and mission binding fields unchanged.

- [ ] **Step 3: Regenerate the deterministic Stage 5D fixture.**

  ```powershell
  $project = (Get-Location).Path
  & D:\PX4PSP\Python38\python.exe future_aircraft_ws\src\multi_uav_mission\scripts\mavros_smoke_check.py --live-config config\stage5_live_mission.json --backend dry-run --report "$env:TEMP\future_aircraft_stage5d_odom.json"
  ```

  Inspect the report: both `odom_topic` checks must target `mavros/odometry/in`; then replace `tests/fixtures/stage5d/expected_mavros_smoke_report.json` with that exact JSON plus its final newline.

- [ ] **Step 4: Verify green and retain LF line endings.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
  ```

  Also inspect the WSL script bytes and reject CRLF:

  ```powershell
  $b = [System.IO.File]::ReadAllBytes('scripts/wsl/stage2_two_mavros.sh')
  if (0..($b.Length - 2) | Where-Object { $b[$_] -eq 13 -and $b[$_ + 1] -eq 10 }) { throw 'CRLF found' }
  ```

- [ ] **Step 5: Commit the implementation.**

  ```powershell
  git add scripts/wsl/stage2_two_mavros.sh config/stage5_live_mission.json tests/fixtures/stage5d/expected_mavros_smoke_report.json
  git commit -m "fix: use PX4 odometry stream for live smoke"
  ```

### Task 3: Document the changed interface and run the no-arm live check

**Files:**
- Modify: `.agents/AGENT2READ.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-30-stage-6d-odometry-stream-design.md`

**Interfaces:**
- Consumes: the validated project contract and Stage 6D live report.
- Produces: accurate operator instructions: `LOCAL_POSITION_NED` maps to local pose/velocity; Stage 6D odom readiness uses MAVROS `odometry/in` from PX4 `ODOMETRY`.

- [ ] **Step 1: Update operator and agent documentation.**

  Replace claims that Stage 6D waits for `local_position/odom` with the exact `odometry/in` topic names.  State that it is the output of PX4 `ODOMETRY` through MAVROS extras; retain the prohibition on entering Stage 6E until a fresh Stage 6D report passes.

- [ ] **Step 2: Run final offline validation.**

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage5d.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
  powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
  ```

  Expected: all exit with code 0.  This proves contract consistency only; it does not prove the live topic exists.

- [ ] **Step 3: Restart the GUI stack and collect only read-only live evidence.**

  Start a new, clean GUI simulation using:

  ```powershell
  scripts\start_two_uav.bat
  ```

  Confirm the MAVROS startup logs identify the extras `odom` plugin, then run:

  ```powershell
  scripts\run_live_no_arm_smoke.bat
  ```

  Inspect `logs/stage6d_live/mavros_smoke_report.json`.  It must report ready `state_topic`, `odom_topic` at `/uav*/mavros/odometry/in`, and both required services for both UAVs.  Do not run Stage 6E, arm, set mode, or publish setpoints during this task.

- [ ] **Step 4: Commit documentation only after offline validation.**

  ```powershell
  git add .agents/AGENT2READ.md README.md docs/superpowers/specs/2026-07-30-stage-6d-odometry-stream-design.md
  git commit -m "docs: describe Stage 6D odometry stream"
  ```

## Self-Review

- Spec coverage: Tasks 1 and 2 implement the stream and smoke-contract change; Task 3 satisfies the required documentation update and separates offline evidence from a fresh no-arm live report.
- Placeholder scan: no unresolved implementation placeholders remain.
- Interface consistency: the only new live odom binding is consistently `/uav*/mavros/odometry/in`; local pose remains supplied by `LOCAL_POSITION_NED`.
