@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 7 live SLAM ego-swarm simulation-arm flight runner
  echo [DRY-RUN] 1. require --allow-arm --simulation-only for live flight
  echo [DRY-RUN] 2. validate the current run and simulation instance sensor readiness report
  echo [DRY-RUN] 3. run ego_swarm_flight_smoke_check.py --backend ros --timeout-s 10
  echo [DRY-RUN] 4. start setpoint bridges only after both no-arm checks pass
  echo [DRY-RUN] 5. run mission_executor.py --backend ros --allow-arm --simulation-only
  echo [DRY-RUN] 6. verify OFFBOARD, arming, takeoff altitude, short flight segment, and landing
  echo [DRY-RUN] 7. write flight_report.json, mission_events.jsonl, executor_trace.json, score_summary.json
  exit /b 0
)
set ALLOW_ARM=0
set SIMULATION_ONLY=0
for %%A in (%*) do (
  if /I "%%~A"=="--allow-arm" set ALLOW_ARM=1
  if /I "%%~A"=="--simulation-only" set SIMULATION_ONLY=1
)
if "%ALLOW_ARM%" NEQ "1" (
  echo [ERROR] Stage 7 flight requires --allow-arm.
  exit /b 1
)
if "%SIMULATION_ONLY%" NEQ "1" (
  echo [ERROR] Stage 7 flight requires --simulation-only.
  exit /b 1
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
start "futureAircraftSim Stage 7 sim-arm flight" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_live_slam_ego_swarm_flight.sh' %*"
exit /b 0
