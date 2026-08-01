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
  exit /b 0
)
set TEMP_SCRIPT=%TEMP%\future_aircraft_stage2_uavsitl.bat
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lines = Get-Content -LiteralPath $env:RFLYSIM_UAV_SITL_SCRIPT; $kept = New-Object System.Collections.Generic.List[string]; foreach ($line in $lines) { if ($line -match '^NET SESSION ') { continue }; if ($line -match '^REM kill all applications when press a key') { $kept.Add('REM FutureAircraftSim: original automatic cleanup block removed for noninteractive live runs.'); $kept.Add('ECHO FutureAircraftSim SITL wrapper ended without automatic cleanup. Run scripts\kill_all.bat when needed.'); break }; $kept.Add($line) }; $src = ($kept -join [Environment]::NewLine); $src = $src.Replace('echo Press any key to exit; read -n 1', 'echo FutureAircraftSim SITL running. Close this WSL process or window to stop.; tail -f /dev/null'); $src = $src.Replace('SET PosXStr=-0.1', 'SET PosXStr=' + $env:STAGE2_POS_X_STR); $src = $src.Replace('SET PosYStr=-0.8', 'SET PosYStr=' + $env:STAGE2_POS_Y_STR); $src = $src.Replace('SET YawStr=0', 'SET YawStr=' + $env:STAGE2_YAW_STR); $src = $src.Replace('SET UE4_MAP=ChallengeMap', 'SET UE4_MAP=' + $env:RFLYSIM_UE4_MAP); $q = [char]34; $new = 'wsl -d %%RFLYSIM_WSL_DISTRO%% -e bash -lic ' + $q + 'echo Starting PX4 Build; cd %%PSP_PATH_LINUX%%/Firmware; ./BkFile/EnvOri.sh; export PATH=$HOME/ninja:$HOME/gcc-arm-none-eabi-7-2017-q4-major/bin:$PATH; make px4_sitl_default; ./Tools/sitl_multiple_run_rfly.sh %%VehicleNum%% %%START_INDEX%% %%PX4SitlFrame%%; echo FutureAircraftSim SITL running. Close this WSL process or window to stop.; tail -f /dev/null' + $q; $src = [regex]::Replace($src, '(?m)^\s*wsl -d RflySim-20\.04 echo Starting PX4 Build;[^\r\n]*tail -f /dev/null\r?$', { param($m) '    ' + $new }); Set-Content -LiteralPath $env:TEMP_SCRIPT -Value $src -Encoding ASCII"
if not exist "%TEMP_SCRIPT%" (
  echo [ERROR] Failed to generate temporary two-UAV SITL wrapper.
  exit /b 1
)
if /I "%~1"=="--generate-only" (
  echo [OK] Generated %TEMP_SCRIPT%
  exit /b 0
)
start "RflySim SITL uav1/uav2" cmd /k call "%TEMP_SCRIPT%"
exit /b 0

