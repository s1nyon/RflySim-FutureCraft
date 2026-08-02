@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set MAP_NAME=%PREDICTED_COURSE_BASE_MAP%
set SOURCE_PNG=%PREDICTED_COURSE_OUTPUT%\%MAP_NAME%.png
set SOURCE_TXT=%PREDICTED_COURSE_OUTPUT%\%MAP_NAME%.txt
set TARGET_PNG=%RFLYSIM_COPTERSIM_MAP_DIR%\%MAP_NAME%.png
set TARGET_TXT=%RFLYSIM_COPTERSIM_MAP_DIR%\%MAP_NAME%.txt
set BACKUP_PNG=%PREDICTED_COURSE_TERRAIN_BACKUP_DIR%\%MAP_NAME%.png
set BACKUP_TXT=%PREDICTED_COURSE_TERRAIN_BACKUP_DIR%\%MAP_NAME%.txt

if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Deploy flat CopterSim terrain for %MAP_NAME%
  echo [DRY-RUN] source: %PREDICTED_COURSE_OUTPUT%
  echo [DRY-RUN] target: %RFLYSIM_COPTERSIM_MAP_DIR%
  echo [DRY-RUN] backup: %PREDICTED_COURSE_TERRAIN_BACKUP_DIR%
  exit /b 0
)

if /I "%~1"=="--restore" goto Restore

if not exist "%SOURCE_PNG%" (
  echo [ERROR] Missing generated terrain: %SOURCE_PNG%
  exit /b 1
)
if not exist "%SOURCE_TXT%" (
  echo [ERROR] Missing generated terrain calibration: %SOURCE_TXT%
  exit /b 1
)
if not exist "%TARGET_PNG%" (
  echo [ERROR] Missing installed terrain to back up: %TARGET_PNG%
  exit /b 1
)
if not exist "%TARGET_TXT%" (
  echo [ERROR] Missing installed terrain calibration to back up: %TARGET_TXT%
  exit /b 1
)

if exist "%BACKUP_PNG%" (
  if not exist "%BACKUP_TXT%" (
    echo [ERROR] Incomplete terrain backup: %PREDICTED_COURSE_TERRAIN_BACKUP_DIR%
    exit /b 1
  )
) else (
  if exist "%BACKUP_TXT%" (
    echo [ERROR] Incomplete terrain backup: %PREDICTED_COURSE_TERRAIN_BACKUP_DIR%
    exit /b 1
  )
  if not exist "%PREDICTED_COURSE_TERRAIN_BACKUP_DIR%" mkdir "%PREDICTED_COURSE_TERRAIN_BACKUP_DIR%"
  if errorlevel 1 exit /b %ERRORLEVEL%
  copy /b "%TARGET_PNG%" "%BACKUP_PNG%" >nul
  if errorlevel 1 exit /b %ERRORLEVEL%
  copy /b "%TARGET_TXT%" "%BACKUP_TXT%" >nul
  if errorlevel 1 exit /b %ERRORLEVEL%
)

copy /b "%SOURCE_PNG%" "%TARGET_PNG%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
copy /b "%SOURCE_TXT%" "%TARGET_TXT%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
fc /b "%SOURCE_PNG%" "%TARGET_PNG%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
fc /b "%SOURCE_TXT%" "%TARGET_TXT%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
echo [OK] Deployed flat CopterSim terrain for %MAP_NAME%
exit /b 0

:Restore
if not exist "%BACKUP_PNG%" (
  echo [ERROR] Missing terrain backup: %BACKUP_PNG%
  exit /b 1
)
if not exist "%BACKUP_TXT%" (
  echo [ERROR] Missing terrain backup calibration: %BACKUP_TXT%
  exit /b 1
)
copy /b "%BACKUP_PNG%" "%TARGET_PNG%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
copy /b "%BACKUP_TXT%" "%TARGET_TXT%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
fc /b "%BACKUP_PNG%" "%TARGET_PNG%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
fc /b "%BACKUP_TXT%" "%TARGET_TXT%" >nul
if errorlevel 1 exit /b %ERRORLEVEL%
echo [OK] Restored original CopterSim terrain for %MAP_NAME%
exit /b 0
