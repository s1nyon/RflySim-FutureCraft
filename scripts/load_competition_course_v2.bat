@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set SPEC=%SCRIPT_DIR%..\config\maps\competition_course_v2.json
set GENERATED=%COMPETITION_COURSE_V2_OUTPUT%
set RECEIPT=%COMPETITION_COURSE_V2_OUTPUT%\load_receipt.json
set LOADER=%SCRIPT_DIR%..\future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_ue_loader.py
if not exist "%GENERATED%\entity_manifest.json" echo [ERROR] Generate Competition Course V2 first. & exit /b 1
if /I "%~1"=="--dry-run" "%PYTHON_EXE%" "%LOADER%" --spec "%SPEC%" --generated "%GENERATED%" --receipt "%RECEIPT%" --asset-path "%COMPETITION_COURSE_V2_ARUCO_ASSET%" --dry-run & exit /b %ERRORLEVEL%
"%PYTHON_EXE%" "%LOADER%" --spec "%SPEC%" --generated "%GENERATED%" --receipt "%RECEIPT%" --asset-path "%COMPETITION_COURSE_V2_ARUCO_ASSET%"
exit /b %ERRORLEVEL%
