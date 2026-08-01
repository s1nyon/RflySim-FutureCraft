@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 7 layered topic probe
  echo [DRY-RUN] 1. load config/stage7_live_slam_ego_swarm.json
  echo [DRY-RUN] 2. load and validate the current run-scoped sensor readiness report
  echo [DRY-RUN] 3. classify checks into sensor_bridge, fast_lio, mavros, ego_swarm, flight_gate
  echo [DRY-RUN] 4. write logs/stage7_live/topic_probe_report.json
  echo [DRY-RUN] 5. no arming, setpoint, or planner goal is published
  exit /b 0
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
start "futureAircraftSim Stage 7 topic probe" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "source /opt/ros/noetic/setup.bash; if [ -f '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash' ]; then source '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash'; fi; source '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_run_context.sh'; stage7_load_run_context '%FUTURE_AIRCRAFT_SIM_WSL_DIR%'; python3 '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/src/multi_uav_mission/scripts/stage7_topic_probe.py' --config '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/config/stage7_live_slam_ego_swarm.json' --backend ros --timeout-s 3 --readiness-report $STAGE7_READINESS_REPORT --run-id $STAGE7_RUN_ID --simulation-instance-id $STAGE7_CURRENT_SIMULATION_INSTANCE_ID --report '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/logs/stage7_live/topic_probe_report.json'; exec bash"
exit /b 0
