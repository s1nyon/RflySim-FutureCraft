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
  echo [DRY-RUN] Generate two-UAV SITL wrapper from %RFLYSIM_UAV_SITL_SCRIPT%
  echo [DRY-RUN] Map: %RFLYSIM_UE4_MAP%
  echo [DRY-RUN] Positions: %STAGE2_POS_X_STR% / %STAGE2_POS_Y_STR% / %STAGE2_YAW_STR%
  echo [DRY-RUN] Expected side effects: RflySim3D, QGroundControl, CopterSim, PX4 SITL for two vehicles
  echo [DRY-RUN] Ownership: GUI processes are registered at creation when STACK_MANIFEST is set
  exit /b 0
)
set TEMP_SCRIPT=%TEMP%\future_aircraft_stage2_uavsitl.bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%..\scripts\lifecycle\generate_sitl_wrapper.ps1" -SourceScript "%RFLYSIM_UAV_SITL_SCRIPT%" -Output "%TEMP_SCRIPT%"
if errorlevel 1 (
  echo [ERROR] Failed to generate temporary two-UAV SITL wrapper.
  exit /b 1
)
if /I "%~1"=="--generate-only" (
  echo [OK] Generated %TEMP_SCRIPT%
  exit /b 0
)

if defined STACK_MANIFEST (
  "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role "cmd:stage_orchestrator" --command-line "cmd /k call %TEMP_SCRIPT%" --file-path "cmd.exe" --arguments "/k call %TEMP_SCRIPT%"
  if errorlevel 1 (
    echo [WARN] SITL wrapper launcher registration failed.
  )
) else (
  start "RflySim SITL uav1/uav2" cmd /k call "%TEMP_SCRIPT%"
)
exit /b 0
