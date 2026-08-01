@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 7 dual FAST-LIO live runner
  echo [DRY-RUN] 1. source ROS Noetic, 28com_uav, and future_aircraft_ws
  echo [DRY-RUN] 2. start CopterSim 1 sensor 0 UDP 9999 as /uav1/rflysim_sensor_bridge
  echo [DRY-RUN] 3. start CopterSim 2 sensor 10 UDP 10009 as /uav2/rflysim_sensor_bridge
  echo [DRY-RUN] 4. adapt independent clouds to /uav1/rflysim/lidar and /uav2/rflysim/lidar
  echo [DRY-RUN] 5. relay independent IMUs to /uav1/rflysim/imu and /uav2/rflysim/imu
  echo [DRY-RUN] 6. start dual FAST-LIO and collect run-scoped no-arm readiness evidence
  echo [DRY-RUN] 7. do not publish planner goals, setpoints, mode requests, or arming requests
  exit /b 0
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
start "futureAircraftSim Stage 7 dual FAST-LIO" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_live_fastlio_dual.sh'"
exit /b 0
