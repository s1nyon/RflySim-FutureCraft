@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 1 single-UAV launch orchestration
  echo [DRY-RUN] 1. start_vcxsrv.bat
  echo [DRY-RUN] 2. start_rflysim_sitl_single.bat
  echo [DRY-RUN] 3. wait %STAGE1_BOOT_WAIT_SECONDS% seconds
  echo [DRY-RUN] 4. start_wsl_ros_single.bat
  exit /b 0
)
call "%SCRIPT_DIR%start_vcxsrv.bat"
start "futureAircraftSim SITL" cmd /k "call ""%SCRIPT_DIR%start_rflysim_sitl_single.bat"""
timeout /t %STAGE1_BOOT_WAIT_SECONDS% /nobreak >nul
start "futureAircraftSim ROS" cmd /k "call ""%SCRIPT_DIR%start_wsl_ros_single.bat"""
exit /b 0


