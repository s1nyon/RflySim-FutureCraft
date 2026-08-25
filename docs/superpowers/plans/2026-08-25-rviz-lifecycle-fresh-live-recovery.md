# RViz Lifecycle Fresh Live Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register optional dual-UAV RViz at process creation, then replace the suspect live instance and verify the unchanged protected tunnel mission on a fresh stack.

**Architecture:** The Windows launcher validates explicit stack identity and passes it through `wsl -e env` to a small WSL wrapper. The wrapper sources the existing overlays, registers its own PID/PGID, and execs the existing RViz launch; no flight, TF, or frame mathematics change. A standard manifest stop/start supplies a fresh runtime boundary before repeating readiness and flight validation.

**Tech Stack:** Windows batch and PowerShell, WSL Bash, ROS Noetic/roslaunch/RViz, repository Python contract tests, manifest lifecycle scripts.

## Global Constraints

- Do not change PX4, MAVROS, Faster-LIO, EGO-Swarm, mission route, setpoint coordinates, TF, frame names, or z sign.
- RViz remains optional, off by default, and outside READY/health/control paths.
- Every live process must be attributable at creation through the current stack manifest.
- Stop and restart only through the standard manifest lifecycle; no name sweep, `pkill`, `taskkill`, or `wsl --shutdown`.
- Arming requires fresh run-scoped readiness, matching simulation-instance identity, `--allow-arm`, `--simulation-only`, and `allow_arm=true`.

---

### Task 1: Enforce RViz lifecycle ownership

**Files:**
- Modify: `tests/rviz_project_contract_check.py`
- Modify: `scripts/run_rflysim_rviz.bat`
- Create: `scripts/wsl/rviz_live.sh`

**Interfaces:**
- Consumes: `--stack-id STACK_ID`, `--manifest STACK_MANIFEST_WINDOWS`, current `stack_manifest.json`, `scripts/wsl/lifecycle_common.sh::stack_register`.
- Produces: registered role `wsl:rviz_session`, then `roslaunch multi_uav_mission rflysim_rviz.launch rviz_mode:=<mode>`.

- [ ] **Step 1: Keep the failing ownership contract test**

Require the Windows launcher to accept explicit stack arguments and delegate to `rviz_live.sh`; require the wrapper to call `stack_register wsl`, use role `wsl:rviz_session`, and `exec roslaunch`.

- [ ] **Step 2: Verify the pre-fix test failed for missing ownership behavior**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\rviz_project_contract_check.py --project-root .
```

Expected historical RED evidence: assertion failure for missing `--stack-id`/wrapper ownership contract.

- [ ] **Step 3: Complete the minimal launcher and wrapper**

The batch parser must reject a live call without explicit stack identity, convert the manifest to WSL form, and invoke:

```text
wsl -d RflySim-20.04 -e env STACK_MANIFEST=$STACK_MANIFEST_WSL RFLY_STACK_ID=$STACK_ID bash $PROJECT_DIR/scripts/wsl/rviz_live.sh $RVIZ_MODE
```

The wrapper must source ROS/overlay setup before enabling Bash nounset, verify X11 and manifest inputs, compute its PGID, register at creation, and exec the existing RViz launch.

- [ ] **Step 4: Run focused GREEN checks**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\rviz_project_contract_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\rviz_frame_adapter_check.py --project-root .
wsl -d RflySim-20.04 -e bash -n /mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/scripts/wsl/rviz_live.sh
cmd /d /c scripts\run_rflysim_rviz.bat dual --stack-id fixture --manifest X:\missing\stack_manifest.json --dry-run
```

Expected: all commands exit 0; dry-run publishes no process.

- [ ] **Step 5: Commit the isolated RViz lifecycle fix**

```powershell
git add scripts/run_rflysim_rviz.bat scripts/wsl/rviz_live.sh tests/rviz_project_contract_check.py
git commit -m "viz: register rviz with live stack lifecycle"
```

### Task 2: Run offline regression before live mutation

**Files:**
- Verify only; no additional production files.

**Interfaces:**
- Consumes: repository validators and current branch.
- Produces: evidence that the launcher change does not alter protected launch/control paths.

- [ ] **Step 1: Validate lifecycle safety**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
```

Expected: exit 0.

- [ ] **Step 2: Validate Stage 7 and Stage 8 contracts**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: both exit 0.

- [ ] **Step 3: Validate repository and documentation**

```powershell
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
```

Expected: exit 0, or a documented unrelated optional timeout that does not affect changed files.

### Task 3: Standard-stop the suspect live instance

**Files:**
- Runtime artifacts only under `logs/live_stack/<stack_id>/`.

**Interfaces:**
- Consumes: current stack manifest and explicit user authorization.
- Produces: no live owned/unknown processes and released required ports.

- [ ] **Step 1: Inspect the exact current manifest**

```powershell
.\sim.ps1 status
```

Record stack ID, manifest, ownership, unknown/stale entries, and disarmed state.

- [ ] **Step 2: Execute the standard stop**

```powershell
.\sim.ps1 stop -Execute
```

Expected: manifest-scoped graceful stop only.

- [ ] **Step 3: Verify clean state**

```powershell
.\sim.ps1 status
```

Expected: no active stack, no unknown/stale process, and required ports free. If the known WSL PGID defect occurs, stop without force-recovery.

### Task 4: Fresh-start and validate managed RViz

**Files:**
- Runtime artifacts only.

**Interfaces:**
- Consumes: `sim.ps1 start -Execute`, the new stack ID/manifest, managed RViz launcher.
- Produces: READY live stack plus truthful per-UAV RViz with lifecycle ownership.

- [ ] **Step 1: Start one fresh stack**

```powershell
.\sim.ps1 start -Execute
```

Expected: health gate PASS and new simulation-instance ID.

- [ ] **Step 2: Validate ROS baseline before RViz**

Confirm dual MAVROS connection, Faster-LIO odometry, EGO nodes/topics, no unknown process, and both UAVs disarmed.

- [ ] **Step 3: Launch dual managed RViz**

```powershell
$context = Get-ChildItem logs\live_stack -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$stackId = $context.Name
$manifest = Join-Path $context.FullName 'stack_manifest.json'
scripts\run_rflysim_rviz.bat dual --stack-id $stackId --manifest $manifest
```

Run it in a non-blocking project-owned Windows launcher.

- [ ] **Step 4: Validate RViz ownership and truthfulness**

Require nodes `future_aircraft_uav1_rviz`, `future_aircraft_uav2_rviz`, `rviz_frame_adapter_uav1`, and `rviz_frame_adapter_uav2`; require manifest role `wsl:rviz_session`, `unknown_suspicious=0`, UAV1 path frame `uav1_camera_init`, and UAV2 path frame `uav2_camera_init`.

### Task 5: Fresh readiness and protected flight

**Files:**
- Runtime evidence only under the new Stage 7 run directory.

**Interfaces:**
- Consumes: new simulation-instance ID, current Stage 7 run ID, unchanged mission and course config.
- Produces: no-arm readiness plus final flight report and landing/disarm evidence.

- [ ] **Step 1: Collect fresh no-arm readiness**

Use the standard Stage 7 readiness sampler against the new run ID and simulation-instance ID. Require identity, schema, freshness, isolation, stationary stability, `ready=true`, and both UAVs disarmed.

- [ ] **Step 2: Run the unchanged mission**

```powershell
scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only --stack-id $stackId --manifest $manifest
```

- [ ] **Step 3: Observe the execution boundary**

Record MAVROS mode/armed state, `/uavX/mavros/setpoint_raw/local` frequency, target z, local-position altitude, mission events, watchdog decisions, collision count, OFFBOARD loss count, landing, and disarm.

- [ ] **Step 4: Decide from evidence**

Pass only if both UAVs complete the existing route and land/disarm. If valid targets again produce no lift, do not change frame math; mark the PX4-to-CopterSim actuator boundary as the blocker and stop.

### Task 6: Final verification and handoff

**Files:**
- Modify only current-truth documentation if fresh evidence changes it.

**Interfaces:**
- Consumes: all offline/live evidence.
- Produces: clean Git state where possible, local commits only, and an evidence-backed report.

- [ ] **Step 1: Review diff and status**

```powershell
git diff --check
git status --short --branch
```

- [ ] **Step 2: Update current truth only if warranted**

Record RViz lifecycle behavior and fresh flight outcome without overstating an incomplete regression.

- [ ] **Step 3: Commit documentation if changed**

Use a truthful local commit message; do not push or merge.

- [ ] **Step 4: Report outcome**

Include changed files, root-cause evidence, validation commands/results, remaining risk, current stack state, and the next smallest action.
