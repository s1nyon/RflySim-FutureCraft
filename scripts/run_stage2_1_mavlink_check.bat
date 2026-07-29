@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 2.1 single-UAV MAVLink return-path verifier
  echo [DRY-RUN] 1. inspect PX4 instance 1 MAVLink status
  echo [DRY-RUN] 2. sample /uav1 MAVROS state, odom, and service availability
  echo [DRY-RUN] 3. write logs/stage2_1_live/mavlink_link_report.json
  echo [DRY-RUN] 4. never publish setpoints or call flight-control services
  exit /b 0
)

if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)

start "futureAircraftSim Stage 2.1 MAVLink check" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_1_single_mavlink_check.sh'"
exit /b 0
