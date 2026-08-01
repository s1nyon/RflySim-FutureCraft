# Future Aircraft Sim Agent Handbook

This file is the machine-oriented operating guide for the repository. Any agent working in this workspace should read the files under `.agents/` before making changes, with this document as the primary source of execution rules and current project state. When a task touches the simulation toolchain, also follow [RFLYSIM_TOOLCHAIN_REFERENCE.md](RFLYSIM_TOOLCHAIN_REFERENCE.md) before diagnosing or changing code.

## Repository Purpose

`future_aircraft_sim` is the simulation-side workspace for a multi-UAV indoor navigation and task-execution challenge. The project reuses the existing `28com_uav` ROS1/PX4/MAVROS stack, then layers a simulation-focused mission workflow on top of it.

## Working Rules

- Do not copy or rewrite the original `28com_uav` project into this repository.
- Keep ROS development inside `future_aircraft_ws`.
- Keep Windows launch orchestration, environment setup, and run wrappers in `scripts/`, `config/`, and related support files.
- Preserve the `/uav1` and `/uav2` namespace contract.
- Keep Stage 5 `mission_events.jsonl` compatibility intact.
- Simulation arming is acceptable in this project when `--simulation-only`, `--allow-arm`, and `simulation_arm_policy.allow_arm=true` all agree.
- Never assume real-hardware arming is allowed; real aircraft must remain manual-arm by default.
- If a task changes an interface, update both this file and the root `README.md`.

## Environment Map

Confirmed local locations under `D:\PX4PSP`:

- `D:\PX4PSP\RflySimAPIs` - RflySim APIs and example material
- `D:\PX4PSP\RflySim3D` - RflySim3D launcher and assets
- `D:\PX4PSP\CopterSim` - CopterSim runtime
- `D:\PX4PSP\Firmware` - PX4 firmware tree used by the simulation stack
- `D:\PX4PSP\Python38\python.exe` - local Python runtime used by validation and helper scripts
- `D:\PX4PSP\WinWSL` - Windows-side WSL helper assets
- `D:\PX4PSP\VcXsrv` - X server bundle used by the WSL launch flow

WSL-side conventions used by the scripts:

- `RFLYSIM_WSL_DISTRO=RflySim-20.04`
- `PSP_PATH_LINUX=/mnt/d/PX4PSP`
- `REF_28COM_UAV_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav`
- `FUTURE_AIRCRAFT_SIM_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim`
- ROS1 Noetic is sourced from `/opt/ros/noetic/setup.bash` inside that distro

## Current State

Validated offline stages:

- Stage 0: workspace and launch scaffold
- Stage 1: single-UAV launch chain
- Stage 2: dual-UAV namespace launch chain
- Stage 4: ego-swarm offline adapter contract
- Stage 5A to Stage 5E: behavior tree, live boundary, executor, smoke checks, and simulation-arm executor
- Stage 6A: ideal target provider bridge
- Stage 6B: simulation-vision target provider bridge
- Stage 6C: live dual-MAVROS smoke runbook
- Stage 6D / 6E: no-arm live smoke runner and simulation-arm live runner
- Stage 7: offline dual-sensor isolation, RflySim-to-Ouster cloud adaptation, run-scoped no-arm readiness, ego-swarm, and guarded simulation-arm flight runner contracts

Current limits:

- Stage 2.1 is a hard gate before Stage 6D/6E: run `scripts\run_stage2_1_mavlink_check.bat` after the selected single-UAV simulation path is started, inspect `logs/stage2_1_live/mavlink_link_report.json`, and proceed only when `status` is `ready`. The legacy Rfly SIL-port report `px4_to_mavros_return_path_blocked` was resolved for the dual path by creating dedicated MAVROS links; it does not mean Stage 6D or Stage 6E has passed.
- Offline validation passes for the staged contracts. Live GUI validation has confirmed dual PX4, dual MAVROS and `state.connected: true`; the Stage 6D odometry input is `/uav*/mavros/odometry/in`, sourced from PX4 MAVLink `ODOMETRY` through MAVROS extras, and still requires fresh end-to-end confirmation.
- Stage 6D dry-run validates the no-arm live runner contract without launching anything.
- Stage 6E dry-run validates the simulation-arm runner contract; real execution first runs dual-MAVROS smoke checks, then may call `/uav1/mavros/cmd/arming` and `/uav2/mavros/cmd/arming` in simulation only when the checks and all arm gates pass.
- Stage 7 dry-run/offline validation covers two identified sensor bridges, exact Ouster point fields/timing, normalized per-UAV LiDAR/IMU, run-scoped readiness validation, dual FAST-LIO, dual ego-swarm, and the guarded flight runner. Live sensor/FAST-LIO readiness and the minimum dual ego-swarm flight loop are proven by the 2026-08-01 runs below. The remaining gap is repeatability, longer/obstacle-rich routes, and full mission integration—not first-flight feasibility.
- `run_live_fastlio_dual.bat` is now the no-arm acceptance entrypoint. It writes `logs/stage7_live/<run-id>/sensor_readiness.json` and `logs/stage7_live/current_run.env`; later planner/flight runners reject missing, stale, cross-run, cross-instance, shared-source, unstable, or armed evidence.
- Vision integration is still staged through deterministic providers rather than real detector inference.
- New live-first direction: the Stage 7 FAST-LIO/faster_lio, project-local ego-swarm, and minimal simulation-arm takeoff/flight/landing loop is proven. Prioritize 3–5 fresh-instance repeat runs, longer collision-free routes, and run-scoped artifact cleanup before reconnecting vision, target detection, and behavior-tree mission logic.

## Live Debug Notes, 2026-07-29

The live toolchain investigation reached Stage 2 and was intentionally stopped before completing Stage 6D/6E live validation. Do not report live validation as complete until a fresh run captures Stage 6D no-arm smoke output and, if requested, Stage 6E simulation-arm output.

Confirmed fixes and operating notes from the live debugging session:

- Windows `cmd` launchers must not use nested quoting like `cmd /k "call ""..."""`; that pattern produced Chinese Windows errors equivalent to "The filename, directory name, or volume label syntax is incorrect" and "The command syntax is incorrect." Use `cmd /k call "..."` for generated `.bat` wrappers.
- `scripts/start_two_uav.bat` should start `start_vcxsrv.bat` before launching RflySim/PX4/MAVROS. VcXsrv is part of the RflySim/WSL GUI path.
- Avoid `timeout /t` inside these noninteractive orchestration windows. Use PowerShell `Start-Sleep` for boot waits.
- WSL shell scripts under `scripts/wsl/*.sh` must stay LF-only. `.gitattributes` enforces this with `scripts/wsl/*.sh text eol=lf`.
- The generated two-UAV SITL wrapper must call WSL as `wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "..."` and must preserve the generated `%VehicleNum%`, `%START_INDEX%`, and `%PX4SitlFrame%` variables.
- `scripts/wsl/stage2_two_mavros.sh` must keep the WSL session alive after starting `roscore` and the two MAVROS launches. Without the final `wait`, `roscore` can start successfully and then shut down when the WSL launch session exits.
- After the keepalive fix, a live process check showed `roscore`, `rosmaster`, two `roslaunch mavros px4.launch` processes, and two `mavros_node` processes running in WSL. This is evidence for Stage 2 process residency only, not a full mission smoke pass.
- `Firmware/Tools/sitl_multiple_run_rfly.sh` reserves `16540/17540` and `16541/17541` for the Rfly SIL/CopterSim link. `scripts/wsl/stage2_two_mavros.sh` must create dedicated PX4 MAVLink links before starting MAVROS: `/uav1` uses `udp://:14601@127.0.0.1:14600`, `/uav2` uses `udp://:14611@127.0.0.1:14610`. Reusing the Rfly SIL ports makes MAVROS stay `connected: False`.

Latest live evidence, 2026-07-30:

- `scripts\start_two_uav.bat` successfully started RflySim3D, two CopterSim processes, two PX4 instances, roscore and two MAVROS nodes.
- After the dedicated-link change, `/uav1/mavros/state` and `/uav2/mavros/state` both reported `connected: True`, `armed: False`, `mode: MANUAL` and `system_status: 3`.
- The previous Stage 6D no-arm smoke was blocked by missing `/uav1/mavros/local_position/odom` and `/uav2/mavros/local_position/odom`. That MAVROS topic requires `LOCAL_POSITION_NED_COV`, which this PX4 build cannot stream. Stage 6D now waits for `/uav1/mavros/odometry/in` and `/uav2/mavros/odometry/in`, the MAVROS outputs of PX4 `ODOMETRY`; `odometry/out` is the reverse input to PX4. Do not treat connection success as a completed mission smoke until a fresh no-arm report passes.

Latest Stage 7 live evidence, 2026-08-01:

- Full dual-UAV flight run `stage7-20260801T101757Z-2497`, simulation instance `px4-bb8094a4352d452e`, completed successfully after `ce7e0a7` shortened the wall-adjacent navigation segment and made reached-goal verification independent of a future planner command. Both UAVs armed in OFFBOARD, took off to 1 m, completed the short ego-swarm segment, landed, and disarmed. `flight_report.json` recorded `ready: true`, `collision_count: 0`, `offboard_loss_count: 0`, `timeout_count: 0`, minimum separation `0.85 m`, and duration `23.5 s`.

- Run `stage7-20260801T082349Z-6875`, simulation instance `px4-ac4e722ff724856a`, saved `logs/stage7_live/stage7-20260801T082349Z-6875/sensor_readiness.json`.
- `identity`, `schema`, `freshness`, `isolation`, and `stationary_stability` all passed; both MAVROS states remained `armed: false`, `mode: MANUAL`, and the report returned `ready: true`.
- Each adapter accepted 17,408 points with the exact 32-byte Ouster field layout. Two independent `run_mapping_online` processes remained active and the FAST-LIO log had no missing-field, fatal, process-died, or segmentation errors.
- Live corrections are committed as `e169acc` (ROS initialization, bounded startup and lifecycle cleanup) and `7c9e363` (namespaced IMU source remaps). No planner goal, setpoint, OFFBOARD, ego-swarm, or arming command was sent.
- A later no-arm run `stage7-20260801T090244Z-5522`, simulation instance `px4-2c74476509ac6faa`, again passed identity, schema, freshness, isolation, and stationary stability with both vehicles disarmed. The first ego-swarm launch then failed before `roslaunch` because sourcing the standalone ego workspace hid the project ROS overlay; `9ad9b4c` restores the project overlay with `--extend`, and `46178c0` aligns the read-only topic probe with the ego runner's 120-second readiness window. The successful `stage7-20260801T101757Z-2497` flight supersedes the earlier “requires fresh live run” status.

## Recommended Next Step

Stage 7's minimum dual-UAV live loop is accepted. Continue from this baseline in the following order:

1. Repeat the complete run 3–5 times on fresh simulation instances and record clean-run rate, duration, minimum separation, collisions, OFFBOARD losses, and timeouts.
2. Increase route length and wall clearance incrementally, retaining a failed offline regression before each defect fix.
3. Move flight artifacts fully under their run directory so historical evidence cannot be confused with the current instance.
4. Reconnect target perception and behavior-tree mission logic only after the live loop is repeatable.

Every simulator restart requires a new run id and simulation instance id. Historical readiness reports remain evidence only and must never authorize a later flight. Simulation flight still requires the explicit `--allow-arm --simulation-only` gates; real aircraft remain manual-arm.

Current Stage 7 entrypoints:

1. `scripts\start_two_uav.bat`
2. `scripts\run_live_fastlio_dual.bat`
3. `scripts\run_live_ego_swarm_dual.bat`
4. `scripts\run_stage7_topic_probe.bat`
5. `scripts\run_live_slam_ego_swarm_flight.bat --allow-arm --simulation-only`

Stage 7 intentionally uses `/uav*/mavros/odometry/out` for FAST-LIO external odometry into MAVROS. Stage 6D still observes `/uav*/mavros/odometry/in` from PX4/MAVROS feedback. Keep those directions distinct.
The raw Stage 7 sources are `/rflysim/sensor0/mid360_lidar` plus `/uav1/rflysim/imu_raw`, and `/rflysim/sensor10/mid360_lidar` plus `/uav2/rflysim/imu_raw`. FAST-LIO consumes only normalized `/uav1/rflysim/{lidar,imu}` and `/uav2/rflysim/{lidar,imu}`.
`scripts\run_stage7_topic_probe.bat` is read-only and writes `logs/stage7_live/topic_probe_report.json` with `sensor_bridge`, `fast_lio`, `mavros`, `ego_swarm`, and `flight_gate` readiness layers. Run it before the Stage 7 simulation-arm flight runner and use it as the first failure triage artifact.

The Stage 7 planner, topic probe, and flight runner reuse the current readiness `run_id` and `simulation_instance_id`. The flight runner validates that evidence before creating setpoint bridges or requesting OFFBOARD/arming and writes `logs/stage7_live/flight_report.json` on executor success and failure. Keep planner goals isolated on `/uav1/planning/goal` and `/uav2/planning/goal`.

This route intentionally skips object detection, target provider, and behavior-tree mission logic.

Offline validation baseline:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
```

## File Map

- `config/` - stage contracts, environment templates, and deterministic fixtures.
- `scripts/` - Windows launchers, validation entry points, and WSL helpers.
- `future_aircraft_ws/` - ROS1 workspace sources for mission logic and adapters.
- `tests/fixtures/` - frozen outputs for offline regression checks.
- `docs/superpowers/` - design notes and implementation plans.
- `.agents/` - machine-oriented instructions and repository operating notes.
- `README.md` - human-facing repository overview.

## Sandbox Note

If the Windows sandbox runner is blocked, non-destructive PowerShell commands may be run directly for read-only inspection, offline validation, and local dry-run checks. Simulation live runners can be launched when the user has explicitly accepted simulation arming risk. Anything that can delete, overwrite broadly, change git history, install or download dependencies, or arm real hardware still requires explicit confirmation.
