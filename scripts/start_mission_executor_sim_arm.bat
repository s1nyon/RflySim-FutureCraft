@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 5E simulation-arm executor launcher
  echo [DRY-RUN] 1. generate live mission plan
  echo [DRY-RUN] 2. execute mission_executor.py --backend ros --allow-arm --simulation-only
  exit /b 0
)
start "futureAircraftSim Stage 5E executor" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage5e_executor_sim_arm.sh'"
exit /b 0
