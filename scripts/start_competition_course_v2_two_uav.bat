@echo off
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set RFLYSIM_UE4_MAP=SLAMScene
set SPAWN_ARGS=%FUTURE_AIRCRAFT_SIM_DIR%\future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_spawn_args.py
set SPAWN_SPEC=%FUTURE_AIRCRAFT_SIM_DIR%\config\maps\competition_course_v2.json
set STAGE2_POS_X_STR=
set STAGE2_POS_Y_STR=
set STAGE2_YAW_STR=
set SPAWN_ENV_FILE=%TEMP%\competition_course_v2_spawn_%RANDOM%_%RANDOM%.bat
"%PYTHON_EXE%" "%SPAWN_ARGS%" --spec "%SPAWN_SPEC%" > "%SPAWN_ENV_FILE%"
if errorlevel 1 del /q "%SPAWN_ENV_FILE%" >nul 2>&1 & echo [ERROR] Failed to derive V2 spawn environment from spec. & exit /b 2
call "%SPAWN_ENV_FILE%"
set SPAWN_RESULT=%ERRORLEVEL%
del /q "%SPAWN_ENV_FILE%" >nul 2>&1
if not "%SPAWN_RESULT%"=="0" echo [ERROR] Failed to apply V2 spawn environment. & exit /b 2
if not defined STAGE2_POS_X_STR echo [ERROR] Failed to derive V2 spawn PosX from spec. & exit /b 2
if not defined STAGE2_POS_Y_STR echo [ERROR] Failed to derive V2 spawn PosY from spec. & exit /b 2
if not defined STAGE2_YAW_STR echo [ERROR] Failed to derive V2 spawn yaw from spec. & exit /b 2
set DRY_RUN=0
set STACK_ID=
set STACK_HEALTH_DIR=
set STACK_MANIFEST=
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--stack-id" set "STACK_ID=%~2"
if /I "%~1"=="--health-dir" set "STACK_HEALTH_DIR=%~2"
if /I "%~1"=="--manifest" set "STACK_MANIFEST=%~2"
shift & goto parse_args
:args_done
if defined STACK_ID (
  if not defined STACK_HEALTH_DIR set "STACK_HEALTH_DIR=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\health"
  if not defined STACK_MANIFEST set "STACK_MANIFEST=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\stack_manifest.json"
)
if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Competition Course V2 two-UAV orchestration
  echo [DRY-RUN] base map: %RFLYSIM_UE4_MAP%
  echo [DRY-RUN] NED PosX: %STAGE2_POS_X_STR%
  echo [DRY-RUN] NED PosY: %STAGE2_POS_Y_STR%
  call "%SCRIPT_DIR%generate_competition_course_v2.bat" --dry-run || exit /b 1
  call "%SCRIPT_DIR%deploy_competition_course_v2_terrain.bat" --dry-run || exit /b 1
  call "%SCRIPT_DIR%start_two_uav.bat" --dry-run || exit /b 1
  call "%SCRIPT_DIR%load_competition_course_v2.bat" --dry-run || exit /b 1
  echo [DRY-RUN] register Competition Course V2 motion controller at creation
  exit /b 0
)
if not defined STACK_MANIFEST echo [ERROR] --stack-id or --manifest is required for owned V2 motion. & exit /b 2
call "%SCRIPT_DIR%generate_competition_course_v2.bat" || exit /b 1
call "%SCRIPT_DIR%deploy_competition_course_v2_terrain.bat" || exit /b 1
call "%SCRIPT_DIR%start_two_uav.bat" || exit /b 1
powershell -NoLogo -NoProfile -Command "Start-Sleep -Seconds ([int]$env:PREDICTED_COURSE_SCENE_WAIT_SECONDS)" || exit /b 1
call "%SCRIPT_DIR%load_competition_course_v2.bat"
set COURSE_LOAD_RESULT=%ERRORLEVEL%
if "%COURSE_LOAD_RESULT%"=="0" (
  set MOTION=%FUTURE_AIRCRAFT_SIM_DIR%\future_aircraft_ws\src\multi_uav_mission\scripts\competition_course_motion.py
  set SPEC=%FUTURE_AIRCRAFT_SIM_DIR%\config\maps\competition_course_v2.json
  set MOTION_EVIDENCE=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\competition_course_motion.json
  set MOTION_STOP=%COMPETITION_COURSE_V2_OUTPUT%\motion.stop
  set MOTION_PID_FILE=%FUTURE_AIRCRAFT_SIM_DIR%\logs\live_stack\%STACK_ID%\competition_course_motion.pid
  "%PYTHON_EXE%" "%SCRIPT_DIR%lifecycle\register_launcher.py" launch --manifest "%STACK_MANIFEST%" --role "windows:competition_course_v2_motion" --command-line "%PYTHON_EXE% !MOTION! --spec !SPEC! --evidence !MOTION_EVIDENCE! --stop-file !MOTION_STOP!" --file-path "%PYTHON_EXE%" --arguments "!MOTION! --spec !SPEC! --evidence !MOTION_EVIDENCE! --stop-file !MOTION_STOP!" --pid-file "!MOTION_PID_FILE!"
  if errorlevel 1 set COURSE_LOAD_RESULT=1
  if "!COURSE_LOAD_RESULT!"=="0" (
    powershell -NoLogo -NoProfile -Command "Start-Sleep -Seconds 2; $p=[int](Get-Content -Raw '!MOTION_PID_FILE!'); if(-not (Get-Process -Id $p -ErrorAction SilentlyContinue)){exit 1}; if(-not (Test-Path -LiteralPath '!MOTION_EVIDENCE!')){exit 2}"
    if errorlevel 1 set COURSE_LOAD_RESULT=1
  )
)
if defined STACK_HEALTH_DIR (
  if not exist "%STACK_HEALTH_DIR%" mkdir "%STACK_HEALTH_DIR%"
  if "%COURSE_LOAD_RESULT%"=="0" (
    "%PYTHON_EXE%" "%SCRIPT_DIR%lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status COURSE_READY --ready true --detail "competition course v2 loaded; motion controller owned"
  ) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status COURSE_READY --ready false --detail "competition course v2 load failed"
  )
  powershell -NoLogo -NoProfile -Command "if((Get-Process RflySim3D,CopterSim -ErrorAction SilentlyContinue).Count -ge 2){exit 0}else{exit 1}"
  if errorlevel 1 (
    "%PYTHON_EXE%" "%SCRIPT_DIR%lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status GUI_READY --ready false --detail "RflySim3D/CopterSim not both present"
  ) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status GUI_READY --ready true --detail "RflySim3D and CopterSim present"
  )
)
exit /b %COURSE_LOAD_RESULT%
