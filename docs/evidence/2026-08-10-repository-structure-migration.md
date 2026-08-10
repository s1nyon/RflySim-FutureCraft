# Repository Structure Migration Evidence

**Date:** 2026-08-10

**Scope:** Repository structure migration, dependency pinning, package ownership, unified offline tooling, documentation curation, and approved runtime cleanup. This record does not claim a live-stack or flight result.

## Commit Boundary

- Pre-implementation design baseline: `49bf7f75faee11a34eac523fd254cdc63cadbc58` (`49bf7f7`).
- Verified implementation tip before this evidence-only commit: `9cd5ace2566fe34bbf51921d56e7ac24b998b39b`.
- Exact root migration range: `49bf7f75faee11a34eac523fd254cdc63cadbc58..9cd5ace2566fe34bbf51921d56e7ac24b998b39b` (baseline excluded, verified tip included).
- The evidence-only commit created from this document follows that range and uses the message `docs: record repository structure migration`.

The range contains the approved design, EGO preservation and submodule work, ROS package separation, developer-workspace metadata, unified simulation CLI, safe lifecycle delegation, bounded log maintenance, current-document reorganization, PBL-1 evidence/runtime cleanup, the curator preflight fix, and the Task 10 retired-path test correction.

## EGO-Swarm Dependency

- Fork URL: `https://github.com/s1nyon/ego-planner-swarm.git`
- Branch: `rflysim-noetic-cxx17-compat`
- Pinned commit: `451d10308fa48f59623ad2d760c96cdccbfc2eff`

The parent gitlink, initialized submodule `HEAD`, local `origin/rflysim-noetic-cxx17-compat`, and fresh `git ls-remote` branch result all resolve to that SHA. The submodule status has no `-` or `+` prefix, and its own status is clean at detached `HEAD`.

Fetchability proof:

```text
git ls-remote https://github.com/s1nyon/ego-planner-swarm.git refs/heads/rflysim-noetic-cxx17-compat
451d10308fa48f59623ad2d760c96cdccbfc2eff  refs/heads/rflysim-noetic-cxx17-compat
exit 0
```

## Deletions and Runtime Cleanup

The exact tracked deletions in the migration range are:

- `docs/prompts/2026-08-03-continue-stage8-static-map.md`
- `future_aircraft_ws/src/.gitkeep`
- `scripts/clone_ego_swarm.bat`
- `scripts/kill_all.bat`
- `scripts/patch_stage4_cmake.ps1`
- `scripts/record_logs.bat`
- `scripts/validate_stage0.ps1`

Task 9 completed only the approved guarded runtime cleanup classes:

- emptied the canonical `logs/` contents while preserving the root, including exactly 19 validated direct `logs/live_stack/*.failed` archives;
- removed in-scope `__pycache__/` directories and `.pyc` files under the documented exclusions;
- removed the registered merged `.worktrees/stage6d-odometry-stream` worktree and its merged local branch;
- removed the clean, pushed, fetchable old `external/ego-planner-swarm` checkout only after matching it to the feature gitlink/submodule/remote SHA.

Fresh read-only assertions on 2026-08-10 found the canonical `logs/` root present with 0 children and 0 failed archives, the old external checkout absent, the old Stage 6D worktree and branch absent, and only the main and project-structure-optimization worktrees registered. No cleanup was repeated in Task 10. The active `.superpowers/sdd` directory is intentionally retained through controller review; its final deletion remains deferred until that review completes.

## Gate Recovery

The first old-path scan exposed one self-match in `tests/developer_workspace_config_check.py`: the negative validator stored the retired path as one literal. The exact scan returned exit 0 with that match, so completion stopped. TDD RED was that failing scan. Commit `9cd5ace2566fe34bbf51921d56e7ac24b998b39b` constructs the same sentinel from path components without changing validator behavior. GREEN evidence was the exact scan with no output and exit 1 (ripgrep's no-match status), plus:

```text
D:\PX4PSP\Python38\python.exe tests\developer_workspace_config_check.py --project-root .
[PASS] root and ROS workspace developer metadata are configured
exit 0
```

After that scoped fix, the entire required sequence below was rerun from Step 1 in exact order.

## Step 1 — Repository and Submodule State

| Exact command | Exit | Fresh result |
| --- | ---: | --- |
| `git status --short --branch` | 0 | `## project-structure-optimization`; clean worktree. |
| `git submodule status` | 0 | Pinned `451d10308fa48f59623ad2d760c96cdccbfc2eff third_party/ego-planner-swarm (remotes/origin/rflysim-noetic-cxx17-compat)` with a leading blank status marker, not `-` or `+`. |
| `git -C third_party/ego-planner-swarm status --short --branch` | 0 | `## HEAD (no branch)` and no dirty paths. |
| `git diff --check` | 0 | No output. |
| `git diff --name-only 49bf7f7..HEAD -- future_aircraft_ws/src/multi_uav_mission/scripts future_aircraft_ws/src/multi_uav_mission/launch` | 0 | No output. |

The old-path gate was run exactly as specified in the Task 10 brief:

```powershell
rg -n "external/ego-planner-swarm|external\\ego-planner-swarm" config scripts tests README.md AGENTS.md .agents
```

It produced no output and exited 1, the expected ripgrep no-match result, proving the active old-path search is empty.

The protected `multi_uav_mission` Python/launch files are unchanged from the `49bf7f7` pre-implementation design baseline.

## Step 2 — Repository, CLI, and Build Gates

| Exact command | Exit | Fresh result |
| --- | ---: | --- |
| `.\sim.ps1 doctor` | 0 | Python, WSL distro, clean pinned submodule, EGO overlay, Catkin metadata, and `/uav1`/`/uav2` configuration passed. The absent optional `config/env_local.bat` was reported only as a warning. |
| `.\sim.ps1 build` | 0 | Catkin build completed; `future_aircraft_mission` and `ego_setpoint_bridge_node` reached 100%. |
| `.\sim.ps1 validate -Suite mission` | 0 | Repository contracts passed and the focused `future_aircraft_mission` build completed. |
| `.\sim.ps1 start` | 0 | Printed the manifest lifecycle and `dev` profile plan with `[DRY-RUN]` steps; no `-Execute` was supplied. |
| `.\sim.ps1 status` | 0 | Read-only result: `no active stack`. |
| `.\sim.ps1 stop` | 0 | Default DryRun invocation; result: `no active stack`; no process was stopped. |
| `.\sim.ps1 clean-logs` | 0 | Default DryRun invocation; reported the feature-worktree log directory absent; no cleanup occurred. |

No `-Execute`, live stack, arming, real stop, or real cleanup command was run.

## Step 3 — Protected Offline Regression Suites

| Exact command | Exit | Fresh result |
| --- | ---: | --- |
| `powershell -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1` | 0 | Lifecycle static, registration, health, topology, ownership, and DryRun contracts passed. |
| `powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1` | 0 | Stage 6C live dual-MAVROS smoke runbook offline validation passed. |
| `powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1` | 0 | Stage 6D/6E live-runner offline validation passed. |
| `powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1` | 0 | Stage 7 live SLAM/EGO-swarm offline validation passed. |
| `powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1` | 0 | Course geometry/artifacts/loader, dynamic LiDAR probe, geofence, flight plan, launch, control-chain DryRun, and Stage 7 dependency passed. |

## Rollback Points

- Dependency: `d0a7e653c71810c6a4656a11e366a0ffe837c3cf` is the safe preserved-patch point before the submodule commit. Revert `6070ade1eeb05ed604f09893904b32e0ade0225a` and then `a901c962f2eaf3c9a379a5be3e40b9f25fb0e40e` to undo the dependency contract and pin while retaining the compatibility patch record. Revert `d0a7e653c71810c6a4656a11e366a0ffe837c3cf` only after separately preserving that patch.
- Package: `6070ade1eeb05ed604f09893904b32e0ade0225a` is the point before package separation; revert `d3e05f0722dff1d8b68ed2f6897c636e29199a16` to undo `future_aircraft_mission` separation. `b94d7b2a2e27501132af41a6e6ced22e08d9eb89` is the immediately following developer-workspace metadata commit and must be reviewed if package paths are rolled back.
- CLI: `b94d7b2a2e27501132af41a6e6ced22e08d9eb89` is the point before the unified CLI. Revert, in reverse implementation order, `5387efe6285a100a3422a73810d8eb3a2136b954`, `4d8ae4a18e8a65ec6bb44f621477c36fdf7e9e0a`, `801ac1e48d3730b3c4b4073a0e009681d53511fc`, and `d37cbdcd02442816f80de19638e49f3c49172994`.
- Docs/runtime evidence: `5387efe6285a100a3422a73810d8eb3a2136b954` is the point before current-document reorganization. Revert `f5ab695c2c6c6eb2783fdf06808023b97c523303`, then `9602023e793d350371e17689efede6f7f12f26b5`, then `c654c010c97f0bc81bd9e000221cac7d7352ded4` to undo curator preflight, curated evidence/runtime cleanup commit, and documentation reorganization. Runtime deletions may require restoration from Git/history or backups rather than a blind cleanup reversal.

## Remaining Live Risk

Offline structure migration validated; live no-arm parity not yet verified

A separately supervised `sim.ps1 start -Execute` no-arm parity check remains a user decision. Any real stop still requires manifest ownership review and explicit execution authorization under `AGENTS.md`.
