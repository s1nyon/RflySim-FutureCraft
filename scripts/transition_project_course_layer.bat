@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set SELECTED=%~1
if /I "%SELECTED%"=="predicted_narrow_course" set RECEIPT=%PREDICTED_COURSE_OUTPUT%\course_transition_receipt.json
if /I "%SELECTED%"=="competition_course_v2" set RECEIPT=%COMPETITION_COURSE_V2_OUTPUT%\course_transition_receipt.json
if not defined RECEIPT echo [ERROR] Expected predicted_narrow_course or competition_course_v2. & exit /b 2
set DRY_RUN_ARG=
if /I "%~2"=="--dry-run" set DRY_RUN_ARG=--dry-run
set TRANSITION=%FUTURE_AIRCRAFT_SIM_DIR%\future_aircraft_ws\src\multi_uav_mission\scripts\course_layer_transition.py
"%PYTHON_EXE%" "%TRANSITION%" --project-root "%FUTURE_AIRCRAFT_SIM_DIR%" --selected "%SELECTED%" --receipt "%RECEIPT%" --rflysim-root "%RFLYSIM_ROOT%" %DRY_RUN_ARG%
exit /b %ERRORLEVEL%
