@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Launch WSL ROS single-UAV script: %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage1_single_uav.sh
  echo [DRY-RUN] Full stack: sensor_pkg/main.py ^> faster_lio mapping_mid360.launch ^> rflysim_ego_swarm_single.launch ^> object_det detection.launch ^> mission_pkg basic_test.launch
  exit /b 0
)
start "futureAircraftSim ROS" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage1_single_uav.sh'"
exit /b 0
