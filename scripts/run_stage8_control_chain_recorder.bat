@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Stage 8 read-only control-chain recorder
  echo [DRY-RUN] 1. load config/stage7_live_slam_ego_swarm.json
  echo [DRY-RUN] 2. load current run context and require a fresh simulation instance
  echo [DRY-RUN] 3. subscribe read-only: planner goal/traj_start_trigger/bspline/pos_cmd, setpoint_raw/local, slam odometry_raw, odometry/out, odometry/in, local_position/odom, mavros/state
  echo [DRY-RUN] 4. write stage8_control_chain.jsonl + stage8_control_chain_summary.json under $STAGE7_RUN_DIR
  echo [DRY-RUN] 5. run stage8_ego_chain_analyzer.py to produce per-goal chain segments [goal -^> trigger -^> bspline -^> pos_cmd]
  echo [DRY-RUN] 6. no Publisher, ServiceProxy, arming, set_mode, or setpoint publishing
  exit /b 0
)
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
start "futureAircraftSim Stage 8 control-chain recorder" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "source /opt/ros/noetic/setup.bash; source '%REF_28COM_UAV_WSL_DIR%/devel/setup.bash'; if [ -f '%EGO_SWARM_WSL_DIR%/devel/setup.bash' ]; then source '%EGO_SWARM_WSL_DIR%/devel/setup.bash'; else echo '[WARN] ego-planner-swarm devel not found; planner pos_cmd recording will be limited'; fi; if [ -f '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash' ]; then source '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash'; fi; source '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage7_run_context.sh'; stage7_load_run_context '%FUTURE_AIRCRAFT_SIM_WSL_DIR%'; python3 '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/src/multi_uav_mission/scripts/stage8_control_chain_recorder.py' --config '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/config/stage7_live_slam_ego_swarm.json' --backend ros --duration-s ${STAGE8_RECORDER_DURATION_SEC:-120} --run-id $STAGE7_RUN_ID --simulation-instance-id $STAGE7_CURRENT_SIMULATION_INSTANCE_ID --min-z -0.5 --max-z 2 --output '$STAGE7_RUN_DIR/stage8_control_chain.jsonl' --watchdog-dir '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/logs/stage7_live'; python3 '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/src/multi_uav_mission/scripts/stage8_ego_chain_analyzer.py' --input '$STAGE7_RUN_DIR/stage8_control_chain.jsonl' --report '$STAGE7_RUN_DIR/stage8_ego_chain_report.json'; exec bash"
exit /b 0
