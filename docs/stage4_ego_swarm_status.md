# Stage 4 Ego-Swarm Status

## Completed Offline Artifacts

- Added `docs/superpowers/specs/2026-07-26-stage-4-ego-swarm-minimal-integration-design.md`.
- Added `docs/superpowers/plans/2026-07-26-stage-4-ego-swarm-minimal-integration.md`.
- Added `scripts/validate_stage4.ps1`.
- Added `config/stage4_ego_swarm.json`.
- Added `future_aircraft_ws/src/multi_uav_mission/scripts/ego_swarm_adapter.py`.
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

## Current Gate

Local clone was not completed because the required command was denied by the execution permission layer:

```bat
cmd /c scripts\clone_ego_swarm.bat
```

When command execution is available, run:

```bat
scripts\clone_ego_swarm.bat
powershell -ExecutionPolicy Bypass -File scripts\validate_stage4.ps1
```

## Known Follow-Up

`future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt` still installs only `score_summary.py`. Add `scripts/ego_swarm_adapter.py` to `catkin_install_python(PROGRAMS ...)` once existing-file edits are available.
