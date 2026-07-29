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

Current limits:

- Stage 2.1 is a hard gate before Stage 6D/6E: run `scripts\run_stage2_1_mavlink_check.bat` after the selected single-UAV simulation path is started, inspect `logs/stage2_1_live/mavlink_link_report.json`, and proceed only when `status` is `ready`. `px4_to_mavros_return_path_blocked` means PX4 received MAVROS traffic while MAVROS did not receive a usable PX4 return stream. This does not mean Stage 6D or Stage 6E has passed.
- Offline validation passes for the staged contracts, but live ROS/PX4/MAVROS/RflySim runtime integration still needs end-to-end confirmation.
- Stage 6D dry-run validates the no-arm live runner contract without launching anything.
- Stage 6E dry-run validates the simulation-arm runner contract; real execution first runs dual-MAVROS smoke checks, then may call `/uav1/mavros/cmd/arming` and `/uav2/mavros/cmd/arming` in simulation only when the checks and all arm gates pass.
- Vision integration is still staged through deterministic providers rather than real detector inference.

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
- `scripts/wsl/stage2_two_mavros.sh` must use the RflySim/PX4 offboard MAVLink ports generated by `Firmware/Tools/sitl_multiple_run_rfly.sh`: `/uav1` uses `fcu_url:=udp://:16540@127.0.0.1:17540`, `/uav2` uses `fcu_url:=udp://:16541@127.0.0.1:17541`. The older `14541/14581` mapping caused MAVROS `connected: False` and no `/mavros/local_position/odom` messages with the current PX4 SITL wrapper.

Observed but not fully resolved before stopping:

- Stage 6D no-arm live smoke was rerun after the port fix. PX4, `roscore`, and dual MAVROS started, but MAVROS still reported `connected: False` because the Windows GUI/simulation processes were not running.
- Direct launch attempts for `D:\PX4PSP\RflySim3D\RflySim3D.exe` and `D:\PX4PSP\CopterSim\CopterSim.exe` from this automation shell returned Windows "Access denied". Treat the current Stage 6D live failure as an environment/desktop execution blocker until those executables can be started from an interactive/elevated Windows session.
- If RflySim3D and CopterSim are started manually, rerun `scripts\run_live_no_arm_smoke.bat` or execute `scripts/wsl/stage6d_live_no_arm_smoke.sh` inside WSL and inspect `logs/stage6d_live/mavros_smoke_report.json`.

## Recommended Next Step

Run the aggressive live path in this order:

1. `scripts\start_two_uav.bat`
2. `scripts\run_live_no_arm_smoke.bat`
3. If no-arm smoke passes, `scripts\run_live_sim_arm.bat`

Offline validation baseline:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
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
