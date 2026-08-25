@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set "RVIZ_MODE=dual"
set "DRY_RUN=0"
set "STACK_ID_ARG="
set "STACK_MANIFEST_ARG="

if not "%~1"=="" if /I not "%~1"=="--dry-run" if /I not "%~1"=="--stack-id" if /I not "%~1"=="--manifest" (
  set "RVIZ_MODE=%~1"
  shift
)

:parse_args
if "%~1"=="" goto args_parsed
if /I "%~1"=="--dry-run" (
  set "DRY_RUN=1"
  shift
  goto parse_args
)
if /I "%~1"=="--stack-id" (
  if "%~2"=="" goto missing_option_value
  set "STACK_ID_ARG=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--manifest" (
  if "%~2"=="" goto missing_option_value
  set "STACK_MANIFEST_ARG=%~2"
  shift
  shift
  goto parse_args
)
echo [ERROR] Unknown RViz launcher argument: %~1
exit /b 2

:missing_option_value
echo [ERROR] Missing value for RViz launcher argument: %~1
exit /b 2

:args_parsed

if /I not "%RVIZ_MODE%"=="uav1" if /I not "%RVIZ_MODE%"=="uav2" if /I not "%RVIZ_MODE%"=="dual" (
  echo [ERROR] RViz mode must be uav1, uav2, or dual: %RVIZ_MODE%
  exit /b 2
)

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Project RViz mode=%RVIZ_MODE%
  echo [DRY-RUN] X11 readiness: DISPLAY=127.0.0.1:0.0 xdpyinfo
  echo [DRY-RUN] Lifecycle: register wsl:rviz_session at creation using --stack-id/--manifest
  echo [DRY-RUN] ROS launch: multi_uav_mission rflysim_rviz.launch rviz_mode:=%RVIZ_MODE%
  exit /b 0
)

if defined STACK_MANIFEST_ARG set "STACK_MANIFEST=%STACK_MANIFEST_ARG%"
if not defined STACK_MANIFEST if defined STACK_ID_ARG set "STACK_MANIFEST=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID_ARG%\stack_manifest.json"
if not defined STACK_ID_ARG (
  echo [ERROR] Live RViz requires --stack-id so lifecycle ownership is explicit.
  exit /b 3
)
if not defined STACK_MANIFEST (
  echo [ERROR] Live RViz requires --manifest or a resolvable --stack-id.
  exit /b 3
)
if not exist "%STACK_MANIFEST%" (
  echo [ERROR] Stack manifest not found: %STACK_MANIFEST%
  exit /b 3
)
for /f "delims=" %%m in ('powershell -NoLogo -NoProfile -Command "$p='%STACK_MANIFEST%'; if($p -match '^([A-Za-z]):\\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\\','/') } else { $p.Replace('\','/') }"') do set "STACK_MANIFEST_WSL=%%m"
if not defined STACK_MANIFEST_WSL (
  echo [ERROR] Failed to convert stack manifest to WSL path.
  exit /b 3
)

wsl -d %RFLYSIM_WSL_DISTRO% -e env STACK_MANIFEST=!STACK_MANIFEST_WSL! RFLY_STACK_ID=%STACK_ID_ARG% bash %FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/rviz_live.sh %RVIZ_MODE%
exit /b %ERRORLEVEL%
