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
  echo [DRY-RUN] Stage 2 two-UAV launch orchestration
  echo [DRY-RUN] 0. start_vcxsrv.bat
  echo [DRY-RUN] 1. start_rflysim_sitl_two.bat
  echo [DRY-RUN] 2. start_wsl_mavros_two.bat ^(predicate-gated on PX4 sockets and MAVROS connection^)
  echo [DRY-RUN] 3. retain %STAGE2_BOOT_WAIT_SECONDS% seconds for SITL/scene stabilization before returning
  exit /b 0
)
call "%SCRIPT_DIR%start_vcxsrv.bat"
if defined STACK_MANIFEST (
  "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role "cmd:stage_orchestrator" --command-line "cmd /k call %SCRIPT_DIR%start_rflysim_sitl_two.bat" --file-path "cmd.exe" --arguments "/k call %SCRIPT_DIR%start_rflysim_sitl_two.bat"
  if errorlevel 1 echo [WARN] SITL launcher registration failed.
) else (
  start "futureAircraftSim SITL two" cmd /k call "%SCRIPT_DIR%start_rflysim_sitl_two.bat"
)
rem Stage 2 owns bounded, fail-closed predicates for both real PX4 sockets and
rem MAVROS connected state. Launch it immediately so those readiness waits run
rem concurrently with the retained SITL/scene stabilization interval.
if defined STACK_MANIFEST (
  rem /k keeps the registered cmd alive (stable PID for stop) after the batch
  rem completes; the batch itself must never exit early (block parens fixed).
  "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role "cmd:stage_orchestrator" --command-line "cmd /k call %SCRIPT_DIR%start_wsl_mavros_two.bat" --file-path "cmd.exe" --arguments "/k call %SCRIPT_DIR%start_wsl_mavros_two.bat"
  if errorlevel 1 echo [WARN] MAVROS launcher registration failed.
) else (
  start "futureAircraftSim MAVROS two" cmd /k call "%SCRIPT_DIR%start_wsl_mavros_two.bat"
)
powershell -NoLogo -NoProfile -Command "Start-Sleep -Seconds ([int]$env:STAGE2_BOOT_WAIT_SECONDS)"
exit /b 0
