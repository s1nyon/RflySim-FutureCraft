@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if not exist "%RFLYSIM_VCXSRV_DIR%\config1.xlaunch" (
  echo [ERROR] Missing VcXsrv config: %RFLYSIM_VCXSRV_DIR%\config1.xlaunch
  exit /b 1
)
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Start VcXsrv with %RFLYSIM_VCXSRV_DIR%\config1.xlaunch
  exit /b 0
)
cd /d "%RFLYSIM_VCXSRV_DIR%"
tasklist | find /i "vcxsrv.exe" >nul || Xlaunch.exe -run config1.xlaunch
exit /b 0
