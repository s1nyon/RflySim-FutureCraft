# future_aircraft_sim

This directory contains the simulation-side scaffold for the future aircraft multi-UAV task.

## Stage 0 Scaffold

The current scaffold prepares:

- `future_aircraft_ws/src` as the ROS1 Noetic workspace source directory.
- `config/env_template.bat` for shared Windows environment variables.
- `config/uavs.json` for `/uav1` and `/uav2` namespace, sysid, MAVROS URL, takeoff position, hover altitude, and safety distance settings.
- `scripts/*.bat` launch wrappers with `--dry-run` support.
- `scripts/validate_stage0.ps1` as the Stage 0 validation command.
- `logs/` as the mission output root.

## Validate

Run from this directory:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage0.ps1
```

Expected output:

```text
[PASS] Stage 0 scaffold validation passed.
```

## Dry-Run Commands

These commands verify startup orchestration without requiring ROS, PX4, MAVROS, or RflySim to be running:

```bat
scripts\start_single_uav.bat --dry-run
scripts\start_two_uav.bat --dry-run
scripts\start_mavros_uav1.bat --dry-run
scripts\start_mavros_uav2.bat --dry-run
scripts\start_mission.bat --dry-run
scripts\record_logs.bat --dry-run
scripts\kill_all.bat --dry-run
```

## Local Environment Overrides

Keep `config/env_template.bat` under version control as the documented default. If a machine needs local paths or IP values, create:

```text
config/env_local.bat
```

Every launch wrapper loads `env_template.bat` first, then `env_local.bat` if it exists.

## Current Limits

Stage 0 intentionally does not launch real PX4 SITL, MAVROS, RflySim, `ego-swarm`, perception, or behavior tree nodes yet. Non-dry-run commands currently fail with a clear message until the real launch commands are wired in Stage 1.

## Stage 1 Single-UAV Launch

Stage 1 reuses the existing 28com simulation stack instead of modifying it:

- Windows side: `28com_sim\28com_SITL\UAVSITL.bat` starts RflySim3D, QGroundControl, CopterSim, and PX4 SITL.
- WSL side: `scripts/wsl/stage1_single_uav.sh` starts `28com_uav/sensor_pkg/main.py`, then launches `mission_pkg basic_test.launch enable_logging:=true`.
- Orchestrator: `scripts\start_single_uav.bat` starts VcXsrv, SITL, waits for boot, then starts the WSL ROS mission chain.

Validate Stage 1 without launching GUI programs:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage1.ps1
scripts\start_single_uav.bat --dry-run
scripts\start_rflysim_sitl_single.bat --dry-run
scripts\start_wsl_ros_single.bat --dry-run
```

Launch the real single-UAV chain:

```bat
scripts\start_single_uav.bat
```

This command may open RflySim3D, QGroundControl, CopterSim, WSL, xterm, and ROS windows. Keep the RflySim dongle inserted before running it.

If local paths differ, create `config\env_local.bat` and override values from `config\env_template.bat`.

## Stage 2 Two-UAV Namespace Launch

Stage 2 prepares the dual-UAV launch and MAVROS namespace foundation:

- `scripts\start_rflysim_sitl_two.bat` generates a temporary two-vehicle wrapper from the original `28com_sim\28com_SITL\UAVSITL.bat` without modifying the original file.
- `scripts\start_wsl_mavros_two.bat` starts the WSL-side dual MAVROS script.
- `scripts\wsl\stage2_two_mavros.sh` launches MAVROS under `ROS_NAMESPACE=uav1` and `ROS_NAMESPACE=uav2`.
- Expected live topics include `/uav1/mavros/state`, `/uav2/mavros/state`, `/uav1/mavros/local_position/odom`, and `/uav2/mavros/local_position/odom`.

Validate Stage 2 without launching GUI programs:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
scripts\start_two_uav.bat --dry-run
scripts\start_rflysim_sitl_two.bat --generate-only
```

Launch the real two-UAV chain:

```bat
scripts\start_two_uav.bat
```

This command may open RflySim3D, QGroundControl, two CopterSim/PX4 SITL instances, VcXsrv, WSL, xterm, and two MAVROS instances. Stage 2 does not yet run a multi-UAV mission node.
