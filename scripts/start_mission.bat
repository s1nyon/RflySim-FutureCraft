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
  echo [DRY-RUN] Start futureAircraftSim mission supervisor
  echo [DRY-RUN] Expected namespace inputs: /uav1/mavros, /uav2/mavros
  echo [DRY-RUN] Expected outputs: /mission/events, score_summary.json
  exit /b 0
)
echo [ERROR] Real mission launch command is not wired yet. Run with --dry-run for Stage 0 validation.
exit /b 1
