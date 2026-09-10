# WSL PGID Reuse Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox markers for execution tracking.

**Goal:** Correctly recognize a foreign WSL process that has reused both a recorded PID and PGID, retire the stale manifest without signaling that process, then complete a fresh no-arm EGO control-chain validation.

**Architecture:** Keep the frozen manifest schema, ownership rules, and signal sequence unchanged. Change only identity-classification precedence: a live process at the recorded leader PID must pass the recorded start-time and command-line identity before process-group membership can establish a genuine orphan; a mismatch is stale PID/PGID reuse and must fail closed without any signal plan.

**Tech Stack:** Python 3.8 lifecycle helpers and tests, PowerShell lifecycle validation, ROS Noetic in WSL, repository EGO-Swarm overlay.

## Global Constraints

- Do not modify `future_aircraft_ws/src/future_aircraft_mission/` or EGO/Faster-LIO/PX4 core code.
- Do not arm, request OFFBOARD, launch the C++ mission, or publish MAVROS setpoints.
- Do not use name-based process killing, `wsl --shutdown`, forced broad cleanup, or fresh-instance execution.
- Preserve genuine WSL orphan handling when the recorded leader is absent but verified group members remain.
- All real stop/retirement operations must use the manifest lifecycle entry points and fail closed.

---

## Task 1: Add Regression Tests for Reused WSL Leader PID/PGID

**Files:**
- Modify: `tests/lifecycle_inspect_check.py`
- Modify: `tests/lifecycle_stop_check.py`
- Modify: `tests/lifecycle_retire_stale_check.py`

- [ ] Add an inspect fixture where a foreign process occupies the exact recorded WSL PID and PGID but has a different start time and command line.
- [ ] Assert inspect reports `stale_pid_reuse=1`, `owned_orphan=0`, and fail-closed status.
- [ ] Add stop-plan and stop-execute cases for the same condition.
- [ ] Assert no INT/TERM/KILL action is planned, no backend signal method is invoked, and the foreign process remains present.
- [ ] Add retirement coverage showing this state is eligible for metadata-only retirement and emits no signal.
- [ ] Retain existing genuine-orphan assertions unchanged.
- [ ] Run the three focused tests and confirm the new assertions fail before production changes:

```powershell
D:\PX4PSP\Python38\python.exe tests\lifecycle_inspect_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\lifecycle_stop_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\lifecycle_retire_stale_check.py --project-root .
```

## Task 2: Apply the Minimal Identity-Precedence Fix

**Files:**
- Modify: `scripts/lifecycle/stack_inspect.py`
- Modify: `scripts/lifecycle/stack_stop.py`
- Modify: `scripts/lifecycle/stack_retire_stale.py`

- [ ] In inspect classification, evaluate a present recorded WSL leader first: exact identity means owned/alive; identity mismatch means stale PID reuse even when the numeric PGID exists.
- [ ] Classify `owned_orphan` only when the recorded leader PID is absent and process-group members remain.
- [ ] Mirror the same ordering in stop planning so a reused leader/PGID produces no signal actions.
- [ ] Mirror the same admission rule in retirement so stale reuse can be retired metadata-only.
- [ ] Keep stop execution's per-member identity re-verification and signal order unchanged.
- [ ] Re-run the three focused tests and confirm they pass.

## Task 3: Run Offline Lifecycle and Protected-Baseline Gates

**Files:** none

- [ ] Run the complete lifecycle validator:

```powershell
scripts\validate_lifecycle.ps1
```

- [ ] Run Stage 7 and Stage 8 validation because the lifecycle/start chain can affect PBL-1:

```powershell
scripts\validate_stage7.ps1
scripts\validate_stage8.ps1
```

- [ ] Review `git diff` and verify the change is limited to classification logic, tests, and task documentation.

## Task 4: Retire the Proven-Stale Manifest Safely

**Files:** runtime artifact only
- Inspect: `logs/live_stack/stack-20260909T073830Z-51e7b3ef/stack_manifest.json`

- [ ] Run read-only inspect and stale-retirement DryRun.
- [ ] Confirm the exact reused PID/PGID is classified stale, the DryRun contains zero signal actions, and the unrelated VS Code shell identity remains mismatched.
- [ ] Execute metadata-only retirement using the DryRun confirmation token.
- [ ] Run normal stop DryRun and Execute for the retired manifest; require an empty action list and `clean=true`.
- [ ] Verify the foreign WSL shell still exists and was not signaled.

## Task 5: Start a Fresh Protected Live Stack

**Files:** new run-scoped artifacts under `logs/live_stack/<stack_id>/`

- [ ] Start through the frozen entry point only:

```powershell
scripts\sim.ps1 start -Execute
```

- [ ] Record the new `stack_id`, manifest path, health-gate result, and current simulation-instance identity.
- [ ] Inspect the manifest and require the stack to be READY before any ROS planner stimulus.
- [ ] Confirm FAST-LIO and UAV1 EGO processes are present through the existing protected launch chain.

## Task 6: Collect Strict No-Arm EGO Evidence

**Files:** run-scoped diagnostic evidence only

- [ ] In one WSL shell, source exactly and in this order:

```bash
source /opt/ros/noetic/setup.bash
source third_party/ego-planner-swarm/devel/setup.bash
source future_aircraft_ws/devel/setup.bash
```

- [ ] Record `rospack find ego_planner` and require the repository `third_party/ego-planner-swarm` path, never `/root/catkin_ws`.
- [ ] Record UAV1 EGO node subscriptions and require odometry to resolve to `/uav1/mavros/odometry/out`.
- [ ] Record `/uav1/mavros/odometry/out` publishers/subscribers and require an EGO subscriber.
- [ ] Verify no active EGO subscription remains on publisher-less `/odom_world` or `/grid_map/odom`.
- [ ] Record MAVROS state and require `armed: False` before stimulus.
- [ ] Publish one bounded `geometry_msgs/PoseStamped` goal at `(1,0,1)` on `/uav1/planning/goal`; do not run the mission or publish PX4 setpoints.
- [ ] Record `rostopic type`, sample messages, and a bounded frequency measurement for `/uav1/planning/pos_cmd`; require sustained `quadrotor_msgs/PositionCommand` output.
- [ ] Record MAVROS state again and require `armed: False` and no OFFBOARD transition.
- [ ] Determine PASS/FAIL directly from the collected overlay, graph, message, frequency, and arm-state evidence.

## Task 7: Stop the Fresh Stack and Publish Current Truth

**Files:**
- Create: `docs/evidence/2026-09-10-no-arm-ego-overlay-live-validation.md`
- Modify: `.agents/AGENT2READ.md` only if fresh evidence changes Current Truth

- [ ] Stop via `live_stack_stop.ps1 -DryRun` followed by `-Execute` against the exact new manifest.
- [ ] Require ownership checks to pass and final `clean=true`; do not force retry if verification fails.
- [ ] Document actual `rospack` path, EGO odom subscription, odometry subscriber status, PositionCommand frequency, arm state, stack identity, and final PASS/FAIL.
- [ ] Update Current Truth only with claims supported by the new run-scoped evidence.
- [ ] Re-run relevant documentation/lifecycle checks, review the final diff, and create a local commit without pushing.
