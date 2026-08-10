# RflySim Toolchain Reference Guide

## Purpose

Use this guide when a `future_aircraft_sim` task touches RflySim runtime behavior, ROS1/Noetic, MAVROS, PX4 SITL, CopterSim, RflySim3D, WSL launch flow, MAVLink/UDP, or RflySim vision and robot-competition interfaces. It is a required, scoped reading workflow: find the applicable reference before diagnosing or changing project code.

Do not scan the entire RflySim installation. Read the smallest relevant project file first, then the closest matching toolchain script, API document, or runnable example.

## Working Boundary

- Treat `future_aircraft_sim` as the editable project.
- Treat `future_aircraft_ws/src/future_aircraft_mission` competition behavior and control intent as human-owned by default; simulation orchestration, project adapters, diagnostics, maintenance, and tests are Agent-owned by default.
- Treat ROS interfaces, launch composition, package manifests, lifecycle/launcher code, and any PBL-1-impacting file as a change-gated shared boundary.
- Treat `28com_sim/UAV_demo/28com_uav` as a reference implementation. Do not copy, rewrite, or edit it unless the user explicitly requests a change there.
- Treat `RflySim3D`, `CopterSim`, `Firmware`, `WinWSL`, and general `RflySimAPIs` examples as installed-toolchain material. Inspect them to understand behavior; do not modify them for a project-local fix.
- Preserve `/uav1` and `/uav2`, the Stage 5 event contract, and the simulation-only arming gates described in `AGENT2READ.md`.
- For a behavior or integration question, distinguish verified local evidence from assumptions and from vendor/example behavior.
- Use the [current competition roadmap](../docs/current/competition-roadmap.md) for active priorities and [incidents](../docs/incidents/) only for historical diagnosis.

## Required Reading Sequence

1. Read the directly involved file in this repository: `config/`, `scripts/`, `future_aircraft_ws/`, tests, and the current log/report.
2. Identify the subsystem using the table below.
3. Read the named reference path and the nearest runnable/example implementation. Use targeted `rg` searches instead of broad recursive scans.
4. Compare interfaces: executable/launch order, namespaces, MAVLink ports, ROS topics/services, environment variables, and line endings where applicable.
5. Make the smallest project-local change. Run the relevant offline validator before suggesting a live run.

## Problem-to-Reference Map

| Problem signal | Read in this project first | Then inspect in the toolchain |
| --- | --- | --- |
| RflySim/PX4 startup, missing processes, maps, CopterSim or RflySim3D behavior | `scripts/start_two_uav.bat`, `scripts/start_rflysim_sitl_two.bat`, `config/environment.local.example.bat` | `../28com_sim/28com_SITL/UAVSITL.bat`, `D:\PX4PSP\RflySim3D`, `D:\PX4PSP\CopterSim`, and `D:\PX4PSP\Firmware/Tools/sitl_multiple_run_rfly.sh` |
| Dual-UAV PX4 SITL, vehicle index, ports, model/frame, or generated wrapper | `scripts/start_rflysim_sitl_two.bat`, `config/stage2_two_uav.json`, `scripts/validate_stage2.ps1` | `../28com_sim/28com_SITL/UAVSITL.bat` and `D:\PX4PSP\Firmware/Tools/sitl_multiple_run_rfly.sh` |
| ROS1, WSL, roscore, MAVROS connection, namespaces, or FCU URL | `scripts/wsl/stage2_two_mavros.sh`, `scripts/start_wsl_mavros_two.bat`, `future_aircraft_ws/src/multi_uav_mission/scripts/mavros_smoke_check.py` | `../28com_sim/UAV_demo/28com_uav` (its launch files, ROS packages, and built workspace), plus `D:\PX4PSP\WinWSL` if the issue involves Windows/WSL display or launch setup |
| OFFBOARD, arming, mode setting, takeoff/land, MAVROS services or message types | `mission_executor.py`, `live_mission_contract.py`, `simulation_arm_policy` configuration and Stage 5/6 validators | `../28com_sim/UAV_demo/28com_uav` for existing flight/mission behavior; use MAVROS/PX4 upstream documentation only after confirming the local launch and port contract |
| Vision sensor data, camera/lidar protocol, target detection, segmentation, or simulation perception | `target_provider.py`, `sim_vision_target_provider.py`, Stage 6A/6B config and validators | `D:\PX4PSP\RflySimAPIs\8.RflySimVision\VisionSensorAPI.pdf`, `8.RflySimVision/0.ApiExps/1-UsageAPI`, and `8.RflySimVision/1.BasicExps` |
| Future Aircraft / robot-competition scene, vehicle asset, competition topic, or task semantics | the affected mission/target-provider code and current project README | `D:\PX4PSP\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv`, especially sibling `28com_sim` and `1.BasicExps/7.RobotCom26Basic` |
| UDP/MAVLink packet, external simulator connector, or RflySim API usage | the local caller, environment config, and recorded logs | `D:\PX4PSP\RflySimAPIs\RflySimSDK` and the closest relevant example beneath `RflySimAPIs` |
| PX4 firmware build, SITL target, shell environment, or runtime port generation | generated SITL wrapper and WSL scripts | `D:\PX4PSP\Firmware`, especially `Tools/sitl_multiple_run_rfly.sh`; do not change firmware merely to work around a project-script error |

Paths beginning with `../` are relative to this project root.

## Local Facts That Override Generic Examples

- This project uses ROS1 Noetic in the `RflySim-20.04` WSL distro.
- The two MAVROS namespaces are `/uav1` and `/uav2`.
- Rfly SIL uses `16540/17540` and `16541/17541` internally for CopterSim. MAVROS must use project-created dedicated links: `udp://:14601@127.0.0.1:14600` for `/uav1` and `udp://:14611@127.0.0.1:14610` for `/uav2`.
- `scripts/wsl/*.sh` must remain LF-only.
- A successful process launch does not prove a successful mission. Use the Stage 6D no-arm smoke path before the Stage 6E simulation-arm path.
- Never infer that real-hardware arming is permitted from a simulation example.

## Search Pattern

Start with a narrow search from the project root, then a narrow search in the mapped reference directory:

```powershell
rg -n "<topic-or-error>" scripts config future_aircraft_ws tests
rg -n "<topic-or-error>" ..\28com_sim\UAV_demo\28com_uav
```

For installed components, use an explicit directory, for example:

```powershell
rg -n "<topic-or-error>" D:\PX4PSP\Firmware\Tools
rg -n "<topic-or-error>" D:\PX4PSP\RflySimAPIs\8.RflySimVision\1.BasicExps
```

Exclude generated builds, logs, caches, and third-party/vendor trees unless the failure is inside that dependency.

## Verification Rule

Documentation and examples explain intended behavior; local scripts, live reports, and validators establish the current project behavior. For any change related to the toolchain, run the narrowest matching `scripts/validate_stage*.ps1` check. Do not claim end-to-end RflySim/PX4/MAVROS success without a fresh live run and its recorded output.
