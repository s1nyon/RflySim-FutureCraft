@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set COURSE_SPEC=%SCRIPT_DIR%..\config\maps\competition_course_v2.json
set COURSE_OUTPUT=%COMPETITION_COURSE_V2_OUTPUT%
set COURSE_GENERATOR=%SCRIPT_DIR%..\future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_artifacts.py
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Generate Competition Course V2
  echo [DRY-RUN] spec: %COURSE_SPEC%
  echo [DRY-RUN] output: %COURSE_OUTPUT%
  exit /b 0
)
if not exist "%PYTHON_EXE%" echo ERROR: Python not found: %PYTHON_EXE% & exit /b 2
if not exist "%COURSE_SPEC%" echo ERROR: course spec not found: %COURSE_SPEC% & exit /b 3
"%PYTHON_EXE%" "%COURSE_GENERATOR%" --spec "%COURSE_SPEC%" --output "%COURSE_OUTPUT%"
exit /b %ERRORLEVEL%
