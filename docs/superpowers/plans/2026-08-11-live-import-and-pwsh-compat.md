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

- [x] Add a test that places a non-exporting Catkin-style helper relay ahead of the source scripts directory and executes the real adapter.
- [x] Run `D:\PX4PSP\Python38\python.exe tests\stage7_cloud_contract_check.py --module .../rflysim_cloud_contract.py`; the source-dir `sys.path` fix makes the real adapter import pass.
- [x] Insert the adapter's resolved source directory at the front of `sys.path` before importing `convert_cloud`.
- [x] Re-run the focused test and require exit 0（`stage7 cloud contract: PASS`，见 `docs/evidence/2026-08-11-live-import-and-pwsh-compat-armed-verified.md`）。

### Task 2: PowerShell 7 manifest resolution

**Files:**
- Modify: `tests/sim_cli_check.py`
- Modify: `scripts/sim_cli.psm1`

**Interfaces:**
- Consumes: schema-v2 JSON manifests parsed by either Windows PowerShell 5.1 or PowerShell 7.
- Produces: identical fail-closed active-manifest resolution in both hosts.

- [x] Add a PowerShell 7 fixture that resolves a valid schema-v2 active manifest.
- [x] Run `D:\PX4PSP\Python38\python.exe tests\sim_cli_check.py --project-root .`; PS7 整数判定修复后 PASS。
- [x] Replace the runtime-specific `[int]` check with a safe integral conversion/equality check for schema version `2`（`-is [int] -or -is [long]`）。
- [x] Re-run the CLI test and require exit 0 under both hosts（`[PASS] simulation CLI contracts`）。

### Task 3: Offline gates and live flight

**Files:**
- Runtime evidence only: `logs/`.

**Interfaces:**
- Consumes: `sim.ps1`, protected Stage 7 runners, current run readiness, simulation arm policy.
- Produces: fresh no-arm and armed-live evidence plus a clean stop manifest.

- [x] Run lifecycle, Stage 7, Stage 8, mission-suite, and repository validation gates（lifecycle/6c/6d/7/8/repository 全 PASS）。
- [x] Run `powershell.exe -File .\sim.ps1 start -Profile dev -Execute`；fresh 栈健康门与 sensor readiness 全 PASS；EGO 双节点上线（readiness 120s 新鲜窗内需手动补齐 fastlio→ego→flight 背靠背时序）。
- [x] Run the protected flight runner with exactly `--allow-arm --simulation-only`；双机 OFFBOARD/arm/起飞/14 段导航/降落，`success=true` 41.5s。
- [x] Inspect, DryRun stop, execute manifest stop：zero owned-alive/orphan/unknown 与零端口占用达成；WSL PGID kill 失效需按显式 PID 补清后收尾 `clean: true`（已知缺陷，见 incident）。
- [x] Review `git diff`，commit scoped code/tests/docs（`5d4eaef` 已提交；文档整理后随本批提交），push 需用户明确授权。
