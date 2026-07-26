@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Launch WSL two-UAV MAVROS script: %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh
  echo [DRY-RUN] Expected topics: /uav1/mavros/* and /uav2/mavros/*
  exit /b 0
)
start "futureAircraftSim MAVROS two" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh'"
exit /b 0
