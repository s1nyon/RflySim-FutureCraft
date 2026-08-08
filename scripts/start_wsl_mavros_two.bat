@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

rem NOTE: STACK_ID / STACK_HEALTH_DIR / STACK_MANIFEST are inherited from the
rem caller (start_predicted_course_two_uav.bat) and must NOT be cleared here.
rem Arguments only override them.
set DRY_RUN=0
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--stack-id" set "STACK_ID=%~2"
if /I "%~1"=="--health-dir" set "STACK_HEALTH_DIR=%~2"
if /I "%~1"=="--manifest" set "STACK_MANIFEST=%~2"
shift & goto parse_args
:args_done

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Launch WSL two-UAV MAVROS script: %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh
  echo [DRY-RUN] Expected topics: /uav1/mavros/* and /uav2/mavros/*
  echo [DRY-RUN] Health gate: per-status files under logs/live_stack/^<stack_id^>/health/ (GUI_READY/ROSCORE_READY/MAVROS_UAV1_CONNECTED/MAVROS_UAV2_CONNECTED/COURSE_READY)
  exit /b 0
)

if defined STACK_HEALTH_DIR (
  for /f "delims=" %%w in ('powershell -NoLogo -NoProfile -Command "$p='%STACK_HEALTH_DIR%'; if($p -match '^([A-Za-z]):\\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\\','/') } else { $p.Replace('\','/') }"') do set "STACK_HEALTH_DIR_WSL=%%w"
)
if defined STACK_MANIFEST (
  for /f "delims=" %%m in ('powershell -NoLogo -NoProfile -Command "$p='%STACK_MANIFEST%'; if($p -match '^([A-Za-z]):\\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\\','/') } else { $p.Replace('\','/') }"') do set "STACK_MANIFEST_WSL=%%m"
)

if defined STACK_HEALTH_DIR_WSL (
  start "futureAircraftSim MAVROS two" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "STACK_HEALTH_DIR='%STACK_HEALTH_DIR_WSL%' STACK_ID='%STACK_ID%' STACK_MANIFEST='%STACK_MANIFEST_WSL%' bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh'"
) else (
  start "futureAircraftSim MAVROS two" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh'"
)

if defined STACK_HEALTH_DIR_WSL (
  wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "STACK_HEALTH_DIR='%STACK_HEALTH_DIR_WSL%' bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_health_check.sh' --wait-seconds 180"
  if errorlevel 1 (
    echo [ERROR] ROS/MAVROS health gate failed to become ready within 180s.
    exit /b 1
  )
  echo [OK] ROS/MAVROS health gate ready.
)
exit /b 0
