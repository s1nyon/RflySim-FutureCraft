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
    "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role "gui:VcXsrv" --command-line "%RFLYSIM_VCXSRV_DIR%\Xlaunch.exe -run config1.xlaunch" --file-path "%RFLYSIM_VCXSRV_DIR%\Xlaunch.exe" --arguments "-run config1.xlaunch" --working-directory "%RFLYSIM_VCXSRV_DIR%"
    if errorlevel 1 echo [WARN] VcXsrv launcher registration failed.
  ) else (
    Xlaunch.exe -run config1.xlaunch
  )
)
exit /b 0
