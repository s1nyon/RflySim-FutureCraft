# Stage 4 Ego-Swarm Status

## Completed Offline Artifacts

- Added `docs/superpowers/specs/2026-07-26-stage-4-ego-swarm-minimal-integration-design.md`.
- Added `docs/superpowers/plans/2026-07-26-stage-4-ego-swarm-minimal-integration.md`.
- Added `scripts/validate_stage4.ps1`.
- Added `config/stage4_ego_swarm.json`.
- Added `future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py`.
- Added `ego_swarm_adapter.py` to `multi_uav_mission/CMakeLists.txt` through `catkin_install_python(PROGRAMS ...)`.
- Added `tests/fixtures/stage4/expected_ego_swarm_commands.json`.
- Added `scripts/clone_ego_swarm.bat`.

## Official Source

Official repository:

```text
https://github.com/ZJU-FAST-Lab/ego-planner-swarm.git
```

The repository README documents ROS on Ubuntu 16.04, 18.04, or 20.04, then:

```bash
git clone https://github.com/ZJU-FAST-Lab/ego-planner-swarm.git
cd ego-planner-swarm
catkin_make -j1
source devel/setup.bash
roslaunch ego_planner swarm.launch
```

The Stage 4 offline adapter contract is complete and covered by `scripts/validate_stage4.ps1`.

## Current Integration Gate

The official `ego-planner-swarm` source has not been cloned into `future_aircraft_ws/src`; that directory currently contains only the project-owned `multi_uav_mission` package. Consequently, Stage 4 completion means that the adapter interface and deterministic offline validation are in place. It does not mean that the official planner has been built or exercised against live dual-UAV ROS topics.

To begin the planner runtime integration, run:

```bat
scripts\clone_ego_swarm.bat
```

Then build the ROS workspace in WSL and verify the planner topics before connecting them to the live mission executor. Re-run the offline regression after any integration changes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
```

## Remaining Work

- Treat the already built ego-swarm workspace as a runtime dependency instead of copying it into `28com_sim`.
- Build or point `EGO_SWARM_WSL_DIR` at the already built ego-swarm workspace before live use.
- Run `scripts\run_live_ego_swarm_dual.bat` after FAST-LIO/faster_lio localization is publishing usable odometry for both `/uav1` and `/uav2`.
- Confirm planner command output for `/uav1/planning/pos_cmd` and `/uav2/planning/pos_cmd` in `logs/stage7_live/slam_ego_swarm_smoke_report.json`.
- Replace the deterministic adapter-only confidence with saved live planner evidence after Stage 7 FAST-LIO localization is stable.

## Updated Direction, 2026-07-31

The next development target is no longer vision or behavior-tree expansion.
The live path should mirror the useful part of 28comsim's sequence:

```text
sensor_pkg/main.py -> faster_lio mapping_mid360.launch -> ego-swarm -> MAVROS OFFBOARD flight
```

The replacement target is the planner layer inside this project: use
project-local launch/config wrappers to replace 28comsim's ego-planner flow with
ego-swarm while leaving `28com_sim` unchanged.

## Stage 7 Offline Wrapper Status

Added project-local live-first wrappers:

- `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_fastlio_dual.launch`
- `future_aircraft_ws/src/multi_uav_mission/launch/rflysim_ego_swarm_dual.launch`
- `scripts/run_live_fastlio_dual.bat`
- `scripts/run_live_ego_swarm_dual.bat`
- `scripts/run_stage7_topic_probe.bat`
- `scripts/run_live_slam_ego_swarm_flight.bat`
- `future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_flight_smoke_check.py`
- `future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py`

Offline validation is covered by:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
```

Live completion is still pending. Do not mark Stage 7 complete until
`logs/stage7_live/flight_report.json` records both UAVs completing OFFBOARD,
simulation arming, takeoff, short flight, and landing.

Before the live flight runner, use `scripts\run_stage7_topic_probe.bat` to
write `logs/stage7_live/topic_probe_report.json`. That report separates
sensor bridge, FAST-LIO, MAVROS, ego-swarm, and simulation flight gate failures.
