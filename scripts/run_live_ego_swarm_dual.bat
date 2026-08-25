@echo off
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set STACK_ID_ARG=
set STACK_MANIFEST_ARG=
set DRY_RUN=0
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--stack-id" set "STACK_ID_ARG=%~2"
if /I "%~1"=="--manifest" set "STACK_MANIFEST_ARG=%~2"
shift & goto parse_args
:args_done
if "%DRY_RUN%"=="1" (
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
if defined STACK_MANIFEST_ARG set "STACK_MANIFEST=%STACK_MANIFEST_ARG%"
if not defined STACK_MANIFEST if defined STACK_ID_ARG set "STACK_MANIFEST=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID_ARG%\stack_manifest.json"
if defined STACK_MANIFEST (
  for /f "delims=" %%m in ('powershell -NoLogo -NoProfile -Command "$p='%STACK_MANIFEST%'; if($p -match '^([A-Za-z]):\\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\\','/') } else { $p.Replace('\','/') }"') do set "STACK_MANIFEST_WSL=%%m"
  start "futureAircraftSim Stage 7 dual ego-swarm" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "STACK_ID='%STACK_ID_ARG%' STACK_MANIFEST='!STACK_MANIFEST_WSL!' bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_live_ego_swarm_dual.sh'" ^>nul 2^>^&1
) else (
  start "futureAircraftSim Stage 7 dual ego-swarm" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_live_ego_swarm_dual.sh'" ^>nul 2^>^&1
)
exit /b 0
