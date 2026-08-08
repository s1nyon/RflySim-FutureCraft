@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

rem NOTE: STACK_ID / STACK_HEALTH_DIR / STACK_MANIFEST are inherited from the
rem caller (start_predicted_course_two_uav.bat) and must NOT be cleared here.
rem Arguments only override them.
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
  echo %TIME% mavros_wrapper: STACK_ID=%STACK_ID% HEALTH_DIR=%STACK_HEALTH_DIR% MANIFEST=%STACK_MANIFEST% >> "%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\mavros_launch.log"
)

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Launch WSL two-UAV MAVROS script: %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_two_mavros.sh
  echo [DRY-RUN] Expected topics: /uav1/mavros/* and /uav2/mavros/*
  echo [DRY-RUN] Health gate: per-status files under logs/live_stack/^<stack_id^>/health/ (GUI_READY/ROSCORE_READY/MAVROS_UAV1_CONNECTED/MAVROS_UAV2_CONNECTED/COURSE_READY)
  exit /b 0
)

rem Convert Windows paths to WSL paths via direct PowerShell + file reads
rem (for /f cannot handle quoted first tokens; keep goto structure, no parens).
if not defined STACK_HEALTH_DIR goto no_health_dir
powershell -NoLogo -NoProfile -Command "$p='%STACK_HEALTH_DIR%'; if($p -match '^([A-Za-z]):\\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\\','/') } else { $p.Replace('\','/') }" > "%TEMP%\stack_health_dir_wsl.txt"
set /p STACK_HEALTH_DIR_WSL=<"%TEMP%\stack_health_dir_wsl.txt"
if defined STACK_ID echo %TIME% mavros_wrapper: HEALTH_DIR_WSL=%STACK_HEALTH_DIR_WSL% >> "%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\mavros_launch.log"
:no_health_dir
if not defined STACK_MANIFEST goto no_manifest
powershell -NoLogo -NoProfile -Command "$p='%STACK_MANIFEST%'; if($p -match '^([A-Za-z]):\\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\\','/') } else { $p.Replace('\','/') }" > "%TEMP%\stack_manifest_wsl.txt"
set /p STACK_MANIFEST_WSL=<"%TEMP%\stack_manifest_wsl.txt"
if defined STACK_ID echo %TIME% mavros_wrapper: MANIFEST_WSL=%STACK_MANIFEST_WSL% >> "%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\mavros_launch.log"
:no_manifest

if not defined STACK_HEALTH_DIR_WSL goto launch_plain
if defined STACK_ID echo %TIME% mavros_wrapper: launching stage2 with env >> "%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\mavros_launch.log"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\launch_stage2.ps1" -HealthDirWsl "%STACK_HEALTH_DIR_WSL%" -StackId "%STACK_ID%" -ManifestWsl "%STACK_MANIFEST_WSL%"
goto launch_done
:launch_plain
if defined STACK_ID echo %TIME% mavros_wrapper: launching stage2 plain >> "%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\mavros_launch.log"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\launch_stage2.ps1"
:launch_done

if not defined STACK_HEALTH_DIR_WSL goto health_done
wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "STACK_HEALTH_DIR='%STACK_HEALTH_DIR_WSL%' bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_health_check.sh' --wait-seconds 180"
if errorlevel 1 goto health_fail
echo [OK] ROS/MAVROS health gate ready.
goto health_done
:health_fail
echo [ERROR] ROS/MAVROS health gate failed to become ready within 180s.
exit /b 1
:health_done
exit /b 0
