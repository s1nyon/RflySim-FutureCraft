@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set RFLYSIM_UE4_MAP=%PREDICTED_COURSE_BASE_MAP%
set STAGE2_POS_X_STR=%PREDICTED_COURSE_POS_X_STR%
set STAGE2_POS_Y_STR=%PREDICTED_COURSE_POS_Y_STR%
set STAGE2_YAW_STR=%PREDICTED_COURSE_YAW_STR%

if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Predicted narrow-course two-UAV orchestration
  echo [DRY-RUN] base map: %RFLYSIM_UE4_MAP%
  echo [DRY-RUN] NED PosX: %STAGE2_POS_X_STR%
  echo [DRY-RUN] NED PosY: %STAGE2_POS_Y_STR%
  echo [DRY-RUN] yaw degrees: %STAGE2_YAW_STR%
  echo [DRY-RUN] 1. generate_predicted_narrow_course.bat
  call "%SCRIPT_DIR%generate_predicted_narrow_course.bat" --dry-run
  if errorlevel 1 exit /b %ERRORLEVEL%
  echo [DRY-RUN] 2. start_two_uav.bat
  call "%SCRIPT_DIR%start_two_uav.bat" --dry-run
  if errorlevel 1 exit /b %ERRORLEVEL%
  echo [DRY-RUN] 3. load_predicted_narrow_course.bat
  call "%SCRIPT_DIR%load_predicted_narrow_course.bat" --dry-run
  exit /b %ERRORLEVEL%
)

call "%SCRIPT_DIR%generate_predicted_narrow_course.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
call "%SCRIPT_DIR%start_two_uav.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
call "%SCRIPT_DIR%load_predicted_narrow_course.bat"
exit /b %ERRORLEVEL%
