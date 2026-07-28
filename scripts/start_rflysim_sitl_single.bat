@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if not exist "%RFLYSIM_UAV_SITL_SCRIPT%" (
  echo [ERROR] Missing SITL script: %RFLYSIM_UAV_SITL_SCRIPT%
  exit /b 1
)
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Launch RflySim SITL via %RFLYSIM_UAV_SITL_SCRIPT%
  echo [DRY-RUN] Expected side effects: RflySim3D, QGroundControl, CopterSim, PX4 SITL
  exit /b 0
)
start "RflySim SITL uav1" cmd /k "call ""%RFLYSIM_UAV_SITL_SCRIPT%"""
exit /b 0
