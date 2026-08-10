# Live Import and PowerShell Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the `dev` live chain and complete one explicitly authorized simulation-only armed flight.

**Architecture:** Fix the two observed boundary defects at their sources: Python module resolution in the adapter process and numeric schema validation in the root PowerShell CLI. Preserve every existing readiness, ownership, arming, and stop gate.

**Tech Stack:** ROS1 Noetic, Catkin Python relay scripts, PowerShell 5.1/7, Python 3.8, RflySim/PX4/MAVROS/Faster-LIO/EGO-Swarm.

## Global Constraints

- Do not change mission strategy, EGO tuning, vehicle namespaces, or arming policy.
- Do not bypass a failed readiness report.
- Stop only identities owned by the current stack manifest.
- Keep `scripts/wsl/*.sh` LF-only.

---

### Task 1: Adapter helper resolution

**Files:**
- Modify: `tests/stage7_cloud_contract_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_pointcloud_adapter.py`

**Interfaces:**
- Consumes: sibling module `rflysim_cloud_contract.convert_cloud`.
- Produces: an adapter module that imports correctly even when launched through Catkin's `devel/lib` relay.

- [ ] Add a test that places a non-exporting Catkin-style helper relay ahead of the source scripts directory and executes the real adapter.
- [ ] Run `D:\PX4PSP\Python38\python.exe tests\stage7_cloud_contract_check.py` and require the new assertion to fail with the observed `convert_cloud` import error.
- [ ] Insert the adapter's resolved source directory at the front of `sys.path` before importing `convert_cloud`.
- [ ] Re-run the focused test and require exit 0.

### Task 2: PowerShell 7 manifest resolution

**Files:**
- Modify: `tests/sim_cli_check.py`
- Modify: `scripts/sim_cli.psm1`

**Interfaces:**
- Consumes: schema-v2 JSON manifests parsed by either Windows PowerShell 5.1 or PowerShell 7.
- Produces: identical fail-closed active-manifest resolution in both hosts.

- [ ] Add a PowerShell 7 fixture that resolves a valid schema-v2 active manifest.
- [ ] Run `D:\PX4PSP\Python38\python.exe tests\sim_cli_check.py --project-root .` and require the PowerShell 7 assertion to fail with `malformed stack manifest`.
- [ ] Replace the runtime-specific `[int]` check with a safe integral conversion/equality check for schema version `2`.
- [ ] Re-run the CLI test and require exit 0 under both hosts.

### Task 3: Offline gates and live flight

**Files:**
- Runtime evidence only: `logs/`.

**Interfaces:**
- Consumes: `sim.ps1`, protected Stage 7 runners, current run readiness, simulation arm policy.
- Produces: fresh no-arm and armed-live evidence plus a clean stop manifest.

- [ ] Run lifecycle, Stage 7, Stage 8, mission-suite, and repository validation gates.
- [ ] Run `powershell.exe -File .\sim.ps1 start -Profile dev -Execute` and require the current sensor readiness report and EGO session to pass.
- [ ] Run the protected flight runner with exactly `--allow-arm --simulation-only`; do not add bypass flags.
- [ ] Inspect, DryRun stop, execute manifest stop, and require zero owned-alive/orphan/unknown processes and zero occupied required ports.
- [ ] Review `git diff`, commit only the scoped code/tests/docs, and do not push.
