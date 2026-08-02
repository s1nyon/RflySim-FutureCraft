@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set COURSE_SPEC=%SCRIPT_DIR%..\config\maps\predicted_narrow_course_v1.json
set COURSE_OUTPUT=%PREDICTED_COURSE_OUTPUT%
set COURSE_GENERATOR=%SCRIPT_DIR%..\future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_artifacts.py
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Generate predicted narrow course
  echo [DRY-RUN] spec: %COURSE_SPEC%
  echo [DRY-RUN] output: %COURSE_OUTPUT%
  exit /b 0
)
"%PYTHON_EXE%" "%COURSE_GENERATOR%" --spec "%COURSE_SPEC%" --output "%COURSE_OUTPUT%"
exit /b %ERRORLEVEL%
