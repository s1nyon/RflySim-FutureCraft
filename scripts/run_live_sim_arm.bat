@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 6E live simulation-arm runner
  echo [DRY-RUN] 1. generate logs/stage6e_live/live_mission_plan.json
  echo [DRY-RUN] 2. run mavros_smoke_check.py --backend ros --timeout-s 10
  echo [DRY-RUN] 3. ensure sim_vision_target_provider.py exposes /mission/target_provider/query
  echo [DRY-RUN] 4. run mission_executor.py --backend ros --allow-arm --simulation-only
  echo [DRY-RUN] 5. call MAVROS arming services only through simulation_arm_policy gate
  echo [DRY-RUN] 6. verify OFFBOARD, arming, takeoff altitude, and landing through MAVROS telemetry
  echo [DRY-RUN] 7. write mission_events.jsonl, executor_trace.json, score_summary.json
  exit /b 0
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
start "futureAircraftSim Stage 6E sim-arm" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage6e_live_sim_arm.sh'"
exit /b 0
