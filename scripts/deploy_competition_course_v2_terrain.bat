@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set MAP_NAME=SLAMScene
set SOURCE_PNG=%COMPETITION_COURSE_V2_OUTPUT%\%MAP_NAME%.png
set SOURCE_TXT=%COMPETITION_COURSE_V2_OUTPUT%\%MAP_NAME%.txt
set TARGET_PNG=%RFLYSIM_COPTERSIM_MAP_DIR%\%MAP_NAME%.png
set TARGET_TXT=%RFLYSIM_COPTERSIM_MAP_DIR%\%MAP_NAME%.txt
set BACKUP_PNG=%COMPETITION_COURSE_V2_TERRAIN_BACKUP_DIR%\%MAP_NAME%.png
set BACKUP_TXT=%COMPETITION_COURSE_V2_TERRAIN_BACKUP_DIR%\%MAP_NAME%.txt
if /I "%~1"=="--dry-run" echo [DRY-RUN] V2 terrain source: %COMPETITION_COURSE_V2_OUTPUT% & echo [DRY-RUN] target: %RFLYSIM_COPTERSIM_MAP_DIR% & echo [DRY-RUN] backup: %COMPETITION_COURSE_V2_TERRAIN_BACKUP_DIR% & exit /b 0
if /I "%~1"=="--restore" goto Restore
if not exist "%SOURCE_PNG%" echo [ERROR] Missing %SOURCE_PNG% & exit /b 1
if not exist "%SOURCE_TXT%" echo [ERROR] Missing %SOURCE_TXT% & exit /b 1
if not exist "%TARGET_PNG%" echo [ERROR] Missing installed %TARGET_PNG% & exit /b 1
if not exist "%TARGET_TXT%" echo [ERROR] Missing installed %TARGET_TXT% & exit /b 1
if exist "%BACKUP_PNG%" if not exist "%BACKUP_TXT%" echo [ERROR] Incomplete V2 terrain backup. & exit /b 1
if exist "%BACKUP_TXT%" if not exist "%BACKUP_PNG%" echo [ERROR] Incomplete V2 terrain backup. & exit /b 1
if not exist "%COMPETITION_COURSE_V2_TERRAIN_BACKUP_DIR%" mkdir "%COMPETITION_COURSE_V2_TERRAIN_BACKUP_DIR%"
if not exist "%BACKUP_PNG%" copy /b "%TARGET_PNG%" "%BACKUP_PNG%" >nul || exit /b 1
if not exist "%BACKUP_TXT%" copy /b "%TARGET_TXT%" "%BACKUP_TXT%" >nul || exit /b 1
copy /b "%SOURCE_PNG%" "%TARGET_PNG%" >nul || exit /b 1
copy /b "%SOURCE_TXT%" "%TARGET_TXT%" >nul || exit /b 1
fc /b "%SOURCE_PNG%" "%TARGET_PNG%" >nul || exit /b 1
fc /b "%SOURCE_TXT%" "%TARGET_TXT%" >nul || exit /b 1
echo [OK] Deployed Competition Course V2 terrain
exit /b 0
:Restore
if not exist "%BACKUP_PNG%" echo [ERROR] Missing backup %BACKUP_PNG% & exit /b 1
if not exist "%BACKUP_TXT%" echo [ERROR] Missing backup %BACKUP_TXT% & exit /b 1
copy /b "%BACKUP_PNG%" "%TARGET_PNG%" >nul || exit /b 1
copy /b "%BACKUP_TXT%" "%TARGET_TXT%" >nul || exit /b 1
fc /b "%BACKUP_PNG%" "%TARGET_PNG%" >nul || exit /b 1
fc /b "%BACKUP_TXT%" "%TARGET_TXT%" >nul || exit /b 1
echo [OK] Restored terrain present before V2 deployment
exit /b 0
