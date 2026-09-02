@echo off
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set SPEC=%SCRIPT_DIR%..\config\maps\competition_course_v2.json
set GENERATED=%COMPETITION_COURSE_V2_OUTPUT%
set STACK_ID=
set SIMULATION_INSTANCE_ID=
set DRY_RUN=0
set UNLOAD=0
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--unload" set UNLOAD=1
if /I "%~1"=="--stack-id" set "STACK_ID=%~2"
if /I "%~1"=="--simulation-instance-id" set "SIMULATION_INSTANCE_ID=%~2"
shift & goto parse_args
:args_done
if defined STACK_ID (
  set "COURSE_RUNTIME_DIR=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\competition_course_v2"
  set "RECEIPT=%COURSE_RUNTIME_DIR%\load_receipt.json"
  set "MOTION_STOP=%COURSE_RUNTIME_DIR%\motion.stop"
) else (
  if "%DRY_RUN%"=="0" (
    echo [ERROR] Live V2 load/unload requires --stack-id.
    exit /b 2
  )
  set "RECEIPT=%GENERATED%\load_receipt.json"
  set "MOTION_STOP=%GENERATED%\motion.stop"
)
set LOADER=%SCRIPT_DIR%..\future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_ue_loader.py
if not exist "%GENERATED%\entity_manifest.json" echo [ERROR] Generate Competition Course V2 first. & exit /b 1
if "%DRY_RUN%"=="1" (
  "%PYTHON_EXE%" "%LOADER%" --spec "%SPEC%" --generated "%GENERATED%" --receipt "%RECEIPT%" --asset-path "%COMPETITION_COURSE_V2_ARUCO_ASSET%" --stack-id "%STACK_ID%" --simulation-instance-id "%SIMULATION_INSTANCE_ID%" --dry-run
  exit /b !ERRORLEVEL!
)
if "%UNLOAD%"=="1" (
  "%PYTHON_EXE%" "%LOADER%" --spec "%SPEC%" --generated "%GENERATED%" --receipt "%RECEIPT%" --motion-stop-file "%MOTION_STOP%" --unload --stack-id "%STACK_ID%" --simulation-instance-id "%SIMULATION_INSTANCE_ID%"
  exit /b !ERRORLEVEL!
)
if exist "%MOTION_STOP%" del /q "%MOTION_STOP%"
"%PYTHON_EXE%" "%LOADER%" --spec "%SPEC%" --generated "%GENERATED%" --receipt "%RECEIPT%" --asset-path "%COMPETITION_COURSE_V2_ARUCO_ASSET%" --stack-id "%STACK_ID%" --simulation-instance-id "%SIMULATION_INSTANCE_ID%"
exit /b %ERRORLEVEL%
