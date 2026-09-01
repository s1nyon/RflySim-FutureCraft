@echo off
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set SELECTED=
set STACK_ID=
set SIMULATION_INSTANCE_ID=
set DRY_RUN=0
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--stack-id" set "STACK_ID=%~2"
if /I "%~1"=="--simulation-instance-id" set "SIMULATION_INSTANCE_ID=%~2"
if not defined SELECTED if /I "%~1"=="predicted_narrow_course" set SELECTED=predicted_narrow_course
if not defined SELECTED if /I "%~1"=="competition_course_v2" set SELECTED=competition_course_v2
shift & goto parse_args
:args_done
if not defined SELECTED echo [ERROR] Expected predicted_narrow_course or competition_course_v2. & exit /b 2
if defined STACK_ID (
  set "RECEIPT=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\%SELECTED%\transition_receipt.json"
) else (
  if "%DRY_RUN%"=="0" if /I "%SELECTED%"=="competition_course_v2" (
    echo [ERROR] Live V2 transition requires --stack-id.
    exit /b 2
  )
  if /I "%SELECTED%"=="predicted_narrow_course" set RECEIPT=%PREDICTED_COURSE_OUTPUT%\course_transition_receipt.json
  if /I "%SELECTED%"=="competition_course_v2" set RECEIPT=%COMPETITION_COURSE_V2_OUTPUT%\course_transition_receipt.json
)
set DRY_RUN_ARG=
if "%DRY_RUN%"=="1" set DRY_RUN_ARG=--dry-run
set TRANSITION=%FUTURE_AIRCRAFT_SIM_DIR%\future_aircraft_ws\src\multi_uav_mission\scripts\course_layer_transition.py
if defined STACK_ID (
  "%PYTHON_EXE%" "%TRANSITION%" --project-root "%FUTURE_AIRCRAFT_SIM_DIR%" --selected "%SELECTED%" --receipt "%RECEIPT%" --rflysim-root "%RFLYSIM_ROOT%" --stack-id "%STACK_ID%" --simulation-instance-id "%SIMULATION_INSTANCE_ID%" %DRY_RUN_ARG%
  exit /b !ERRORLEVEL!
)
"%PYTHON_EXE%" "%TRANSITION%" --project-root "%FUTURE_AIRCRAFT_SIM_DIR%" --selected "%SELECTED%" --receipt "%RECEIPT%" --rflysim-root "%RFLYSIM_ROOT%" %DRY_RUN_ARG%
exit /b !ERRORLEVEL!
