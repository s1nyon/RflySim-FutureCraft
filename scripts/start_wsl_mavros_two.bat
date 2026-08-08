@echo off
setlocal
set SCRIPT_DIR=%~dp0

rem NOTE: STACK_ID / STACK_HEALTH_DIR / STACK_MANIFEST are inherited from the
rem caller (start_predicted_course_two_uav.bat) and must NOT be cleared here.
rem Arguments only override them. Every step below writes a start/success trace
rem line to logs/live_stack/<stack_id>/mavros_launch.log so a future stall can
rem be localized to a single step.

set STAGE2_TRACE=
if defined STACK_ID (
  for %%I in ("%SCRIPT_DIR%..\logs\live_stack\%STACK_ID%") do set "STAGE2_TRACE=%%~fI\mavros_launch.log"
)
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step 0 start (inherited STACK_ID=%STACK_ID%) >> "%STAGE2_TRACE%"

call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set DRY_RUN=0
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--stack-id" set "STACK_ID=%~2"
if /I "%~1"=="--health-dir" set "STACK_HEALTH_DIR=%~2"
if /I "%~1"=="--manifest" set "STACK_MANIFEST=%~2"
shift & goto parse_args
:args_done

if defined STACK_ID (
  for %%I in ("%SCRIPT_DIR%..\logs\live_stack\%STACK_ID%") do set "STAGE2_TRACE=%%~fI\mavros_launch.log"
)
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step A success (args resolved) STACK_ID=%STACK_ID% HEALTH_DIR=%STACK_HEALTH_DIR% MANIFEST=%STACK_MANIFEST% >> "%STAGE2_TRACE%"

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Launch WSL two-UAV MAVROS script: %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh
  echo [DRY-RUN] Expected topics: /uav1/mavros/* and /uav2/mavros/*
  echo [DRY-RUN] Health gate: per-status files under logs/live_stack/^<stack_id^>/health/ [GUI_READY/ROSCORE_READY/MAVROS_UAV1_CONNECTED/MAVROS_UAV2_CONNECTED/COURSE_READY]
  exit /b 0
)

rem Step B: convert STACK_HEALTH_DIR to a WSL path via a dedicated helper script,
rem read it back with for /f (never blocks on console input), and fail fast if
rem the result is missing/empty.
if not defined STACK_HEALTH_DIR goto no_health_dir
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step B start (convert HEALTH_DIR to WSL) >> "%STAGE2_TRACE%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\to_wsl_path.ps1" -Path "%STACK_HEALTH_DIR%" -OutFile "%TEMP%\stack_health_dir_wsl.txt"
if errorlevel 1 (
  if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step B FAILED [health dir conversion] >> "%STAGE2_TRACE%"
  echo [ERROR] Failed to convert STACK_HEALTH_DIR to a WSL path.
  exit /b 1
)
set STACK_HEALTH_DIR_WSL=
for /f "usebackq delims=" %%P in ("%TEMP%\stack_health_dir_wsl.txt") do set STACK_HEALTH_DIR_WSL=%%P
if not defined STACK_HEALTH_DIR_WSL (
  if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step B FAILED [empty WSL health dir] >> "%STAGE2_TRACE%"
  echo [ERROR] STACK_HEALTH_DIR_WSL is empty after conversion.
  exit /b 1
)
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step B success HEALTH_DIR_WSL=%STACK_HEALTH_DIR_WSL% >> "%STAGE2_TRACE%"
:no_health_dir

rem Step C: convert STACK_MANIFEST to a WSL path.
if not defined STACK_MANIFEST goto no_manifest
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step C start (convert MANIFEST to WSL) >> "%STAGE2_TRACE%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\to_wsl_path.ps1" -Path "%STACK_MANIFEST%" -OutFile "%TEMP%\stack_manifest_wsl.txt"
if errorlevel 1 (
  if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step C FAILED [manifest conversion] >> "%STAGE2_TRACE%"
  echo [ERROR] Failed to convert STACK_MANIFEST to a WSL path.
  exit /b 1
)
set STACK_MANIFEST_WSL=
for /f "usebackq delims=" %%P in ("%TEMP%\stack_manifest_wsl.txt") do set STACK_MANIFEST_WSL=%%P
if not defined STACK_MANIFEST_WSL (
  if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step C FAILED [empty WSL manifest] >> "%STAGE2_TRACE%"
  echo [ERROR] STACK_MANIFEST_WSL is empty after conversion.
  exit /b 1
)
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step C success MANIFEST_WSL=%STACK_MANIFEST_WSL% >> "%STAGE2_TRACE%"
:no_manifest

rem Step D: launch the WSL Stage 2 headless chain (roscore + dual MAVROS).
if not defined STACK_HEALTH_DIR_WSL goto launch_plain
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step D start (launch stage2 with env) >> "%STAGE2_TRACE%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\launch_stage2.ps1" -HealthDirWsl "%STACK_HEALTH_DIR_WSL%" -StackId "%STACK_ID%" -ManifestWsl "%STACK_MANIFEST_WSL%"
if errorlevel 1 (
  if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step D FAILED [launch_stage2] >> "%STAGE2_TRACE%"
  echo [ERROR] Failed to launch WSL Stage 2.
  exit /b 1
)
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step D success (stage2 wsl launched) >> "%STAGE2_TRACE%"
goto launch_done
:launch_plain
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: launching stage2 plain >> "%STAGE2_TRACE%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\launch_stage2.ps1"
if errorlevel 1 (
  echo [ERROR] Failed to launch WSL Stage 2 [plain].
  exit /b 1
)
:launch_done

rem Step E: bounded health-gate wait. The wait itself is fail-fast (180s inside
rem WSL) and the outer WSL call is additionally bounded by a watchdog so a stuck
rem WSL session cannot hang this wrapper forever.
if not defined STACK_HEALTH_DIR_WSL goto health_done
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step E start (health gate wait <=180s) >> "%STAGE2_TRACE%"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\run_wsl_bounded.ps1" -Distro "%RFLYSIM_WSL_DISTRO%" -Command "STACK_HEALTH_DIR='%STACK_HEALTH_DIR_WSL%' bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_health_check.sh' --wait-seconds 180" -TimeoutSeconds 240
if errorlevel 1 goto health_fail
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step E success (health gate all ready) >> "%STAGE2_TRACE%"
echo [OK] ROS/MAVROS health gate ready.
goto health_done
:health_fail
if defined STAGE2_TRACE echo %TIME% mavros_wrapper: step E FAILED (health gate not ready / timeout) >> "%STAGE2_TRACE%"
echo [ERROR] ROS/MAVROS health gate failed to become ready within the deadline.
exit /b 1
:health_done
exit /b 0
