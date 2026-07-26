@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
set LOG_ROOT=%SCRIPT_DIR%..\logs
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Create timestamped run directory under %LOG_ROOT%
  echo [DRY-RUN] Files: mission_events.jsonl, score_summary.json
  exit /b 0
)
for /f "tokens=1-4 delims=/-. " %%a in ("%date%") do set DATE_PART=%%a%%b%%c
for /f "tokens=1-3 delims=:. " %%a in ("%time%") do set TIME_PART=%%a%%b%%c
set TIME_PART=%TIME_PART: =0%
set RUN_DIR=%LOG_ROOT%\%DATE_PART%_%TIME_PART%
mkdir "%RUN_DIR%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Failed to create log directory: %RUN_DIR%
  exit /b 1
)
type nul > "%RUN_DIR%\mission_events.jsonl"
echo {"success": false, "failure_reasons": ["not_scored_yet"]} > "%RUN_DIR%\score_summary.json"
echo %RUN_DIR%
exit /b 0
