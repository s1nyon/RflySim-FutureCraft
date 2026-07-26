@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set LOG_ROOT=%SCRIPT_DIR%..\logs
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Create timestamped log directory under %LOG_ROOT%
  echo [DRY-RUN] Record /uav1 and /uav2 MAVROS state, odom, setpoint, planner and mission events
  exit /b 0
)
call "%SCRIPT_DIR%create_log_run.bat"
echo [ERROR] Real rosbag record command is not wired yet. Use the generated run directory for manual logs.
exit /b 1
