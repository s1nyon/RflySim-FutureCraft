@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set RFLYSIM_UE4_MAP=%PREDICTED_COURSE_BASE_MAP%
set STAGE2_POS_X_STR=%PREDICTED_COURSE_POS_X_STR%
set STAGE2_POS_Y_STR=%PREDICTED_COURSE_POS_Y_STR%
set STAGE2_YAW_STR=%PREDICTED_COURSE_YAW_STR%

set DRY_RUN=0
set STACK_ID=
set STACK_HEALTH_DIR=
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--dry-run" set DRY_RUN=1
if /I "%~1"=="--stack-id" set "STACK_ID=%~2"
if /I "%~1"=="--health-dir" set "STACK_HEALTH_DIR=%~2"
shift & goto parse_args
:args_done

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Predicted narrow-course two-UAV orchestration
  echo [DRY-RUN] base map: %RFLYSIM_UE4_MAP%
  echo [DRY-RUN] NED PosX: %STAGE2_POS_X_STR%
  echo [DRY-RUN] NED PosY: %STAGE2_POS_Y_STR%
  echo [DRY-RUN] yaw degrees: %STAGE2_YAW_STR%
  echo [DRY-RUN] health gate: GUI_READY / ROSCORE_READY / MAVROS_UAV1_CONNECTED / MAVROS_UAV2_CONNECTED / COURSE_READY
  echo [DRY-RUN] 1. generate_predicted_narrow_course.bat
  call "%SCRIPT_DIR%generate_predicted_narrow_course.bat" --dry-run
  if errorlevel 1 exit /b %ERRORLEVEL%
  echo [DRY-RUN] 2. deploy_predicted_course_terrain.bat
  call "%SCRIPT_DIR%deploy_predicted_course_terrain.bat" --dry-run
  if errorlevel 1 exit /b %ERRORLEVEL%
  echo [DRY-RUN] 3. start_two_uav.bat
  call "%SCRIPT_DIR%start_two_uav.bat" --dry-run
  if errorlevel 1 exit /b %ERRORLEVEL%
  echo [DRY-RUN] 4. wait %PREDICTED_COURSE_SCENE_WAIT_SECONDS% seconds before scene load
  echo [DRY-RUN] 5. load_predicted_narrow_course.bat
  call "%SCRIPT_DIR%load_predicted_narrow_course.bat" --dry-run
  exit /b %ERRORLEVEL%
)

call "%SCRIPT_DIR%generate_predicted_narrow_course.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
call "%SCRIPT_DIR%deploy_predicted_course_terrain.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
call "%SCRIPT_DIR%start_two_uav.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
powershell -NoLogo -NoProfile -Command "Start-Sleep -Seconds ([int]$env:PREDICTED_COURSE_SCENE_WAIT_SECONDS)"
if errorlevel 1 exit /b %ERRORLEVEL%
call "%SCRIPT_DIR%load_predicted_narrow_course.bat"
set COURSE_LOAD_RESULT=%ERRORLEVEL%

if defined STACK_HEALTH_DIR (
  if not exist "%STACK_HEALTH_DIR%" mkdir "%STACK_HEALTH_DIR%"
  if "%COURSE_LOAD_RESULT%"=="0" (
    "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status COURSE_READY --ready true --detail "predicted narrow course loaded"
  ) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status COURSE_READY --ready false --detail "course load failed with %COURSE_LOAD_RESULT%"
  )
  powershell -NoLogo -NoProfile -Command "if((Get-Process RflySim3D,CopterSim -ErrorAction SilentlyContinue).Count -ge 2){exit 0}else{exit 1}"
  if errorlevel 1 (
    "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status GUI_READY --ready false --detail "RflySim3D/CopterSim not both present"
  ) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%..\scripts\lifecycle\health_probe.py" write --health-dir "%STACK_HEALTH_DIR%" --stack-id "%STACK_ID%" --status GUI_READY --ready true --detail "RflySim3D and CopterSim present"
  )
)
exit /b %COURSE_LOAD_RESULT%
