@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Launch WSL ROS single-UAV script: %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage1_single_uav.sh
  echo [DRY-RUN] Mission target: mission_pkg basic_test.launch enable_logging:=true
  exit /b 0
)
start "futureAircraftSim ROS" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage1_single_uav.sh'"
exit /b 0
