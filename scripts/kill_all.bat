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
  echo [DRY-RUN] Stop ROS, MAVROS, PX4 SITL, and mission helper processes started by this scaffold
  exit /b 0
)
echo [ERROR] Real cleanup command is not wired yet. Run with --dry-run for Stage 0 validation.
exit /b 1
