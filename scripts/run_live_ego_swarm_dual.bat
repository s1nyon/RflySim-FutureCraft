@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 7 dual ego-swarm live runner
  echo [DRY-RUN] 1. load the current Stage 7 run and simulation instance IDs
  echo [DRY-RUN] 2. validate the fresh run-scoped no-arm sensor readiness report
  echo [DRY-RUN] 3. source ROS Noetic, ego-planner-swarm, and future_aircraft_ws
  echo [DRY-RUN] 4. roslaunch multi_uav_mission rflysim_ego_swarm_dual.launch only after readiness passes
  echo [DRY-RUN] 5. do not publish setpoints, mode requests, or arming requests
  exit /b 0
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
start "futureAircraftSim Stage 7 dual ego-swarm" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_live_ego_swarm_dual.sh'"
exit /b 0
