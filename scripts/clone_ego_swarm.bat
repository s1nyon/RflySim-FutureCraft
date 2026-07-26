@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set REPO_URL=https://github.com/ZJU-FAST-Lab/ego-planner-swarm.git
set EXTERNAL_DIR=%SCRIPT_DIR%..\external
set TARGET_DIR=%EXTERNAL_DIR%\ego-planner-swarm

if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] git clone %REPO_URL% "%TARGET_DIR%"
  exit /b 0
)

if exist "%TARGET_DIR%\.git" (
  echo [INFO] ego-planner-swarm already exists: %TARGET_DIR%
  exit /b 0
)

if exist "%TARGET_DIR%" (
  echo [ERROR] Target exists but is not a git repository: %TARGET_DIR%
  exit /b 1
)

mkdir "%EXTERNAL_DIR%" >nul 2>&1
git clone %REPO_URL% "%TARGET_DIR%"
if errorlevel 1 (
  echo [ERROR] Failed to clone ego-planner-swarm from %REPO_URL%
  exit /b 1
)

echo [PASS] Cloned ego-planner-swarm to %TARGET_DIR%
exit /b 0
