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
tasklist | find /i "vcxsrv.exe" >nul
if errorlevel 1 (
  if defined STACK_MANIFEST (
    powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\register_launcher.ps1" `
      -Manifest "%STACK_MANIFEST%" -Role "gui:VcXsrv" -FilePath "%RFLYSIM_VCXSRV_DIR%\Xlaunch.exe" `
      -Arguments "-run config1.xlaunch" -WorkingDirectory "%RFLYSIM_VCXSRV_DIR%"
    if errorlevel 1 echo [WARN] VcXsrv launcher registration failed.
  ) else (
    Xlaunch.exe -run config1.xlaunch
  )
)
exit /b 0
