@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set COURSE_SPEC=%SCRIPT_DIR%..\config\maps\predicted_narrow_course_v1.json
set COURSE_REPORT=%SCRIPT_DIR%..\generated\predicted_narrow_course_v1\validation_report.json
set COURSE_LOADER=%SCRIPT_DIR%..\future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_ue_loader.py
if not exist "%COURSE_REPORT%" (
  echo [ERROR] Missing generated validation report: %COURSE_REPORT%
  echo [ERROR] Run scripts\generate_predicted_narrow_course.bat first.
  exit /b 1
)
"%PYTHON_EXE%" "%COURSE_LOADER%" --spec "%COURSE_SPEC%" --validation-report "%COURSE_REPORT%" %*
exit /b %ERRORLEVEL%
