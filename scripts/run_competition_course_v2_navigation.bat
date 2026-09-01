@echo off
setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set "V2_PROFILE="
set "STACK_ID_ARG="
set "STACK_MANIFEST_ARG="
set "ALLOW_ARM=0"
set "SIMULATION_ONLY=0"
set "DRY_RUN=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--profile" (
  set "V2_PROFILE=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--stack-id" (
  set "STACK_ID_ARG=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--manifest" (
  set "STACK_MANIFEST_ARG=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--allow-arm" set "ALLOW_ARM=1"& shift& goto parse_args
if /I "%~1"=="--simulation-only" set "SIMULATION_ONLY=1"& shift& goto parse_args
if /I "%~1"=="--dry-run" set "DRY_RUN=1"& shift& goto parse_args
echo [ERROR] Unknown argument: %~1
exit /b 2

:args_done
if /I not "%V2_PROFILE%"=="short_smoke" if /I not "%V2_PROFILE%"=="full_section_a" (
  echo [ERROR] --profile must be short_smoke or full_section_a.
  exit /b 2
)
if not defined STACK_ID_ARG (
  echo [ERROR] --stack-id is required.
  exit /b 2
)
if not defined STACK_MANIFEST_ARG (
  echo [ERROR] --manifest is required.
  exit /b 2
)

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Competition Course V2 UAV1 Section A profile=%V2_PROFILE%
  echo [DRY-RUN] 1. validate explicit stack manifest and simulation instance identity
  echo [DRY-RUN] 2. validate current run-scoped no-arm sensor readiness
  echo [DRY-RUN] 3. run no-arm EGO control-chain smoke
  echo [DRY-RUN] 4. start UAV1-only setpoint bridge and geofence watchdog
  echo [DRY-RUN] 5. start read-only V2 recorder and RflySim crash recorder
  echo [DRY-RUN] 6. generate the plan from competition_course_v2.json
  echo [DRY-RUN] 7. execute UAV1 mission with explicit simulation arm gates
  echo [DRY-RUN] 8. build provenance-labelled Section A report
  echo [DRY-RUN] no process, OFFBOARD request, or arm request is executed
  exit /b 0
)

if "%ALLOW_ARM%" NEQ "1" (
  echo [ERROR] Live V2 navigation requires --allow-arm --simulation-only.
  exit /b 1
)
if "%SIMULATION_ONLY%" NEQ "1" (
  echo [ERROR] Live V2 navigation requires --allow-arm --simulation-only.
  exit /b 1
)
if not exist "%STACK_MANIFEST_ARG%" (
  echo [ERROR] Explicit stack manifest does not exist: %STACK_MANIFEST_ARG%
  exit /b 1
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)

for /f "delims=" %%m in ('powershell -NoLogo -NoProfile -Command "$p='%STACK_MANIFEST_ARG%'; if($p -match '^([A-Za-z]):\(.*)$'){ '/mnt/' + $matches[1].ToLower() + '/' + ($matches[2] -replace '\','/') } else { $p.Replace('\','/') }"') do set "STACK_MANIFEST_WSL=%%m"
wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "STACK_ID='%STACK_ID_ARG%' STACK_MANIFEST='!STACK_MANIFEST_WSL!' V2_PROFILE='%V2_PROFILE%' bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/competition_course_v2_navigation.sh' --profile '%V2_PROFILE%' --allow-arm --simulation-only"
exit /b %ERRORLEVEL%
