@echo off
setlocal
set SCRIPT_DIR=%~dp0
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"
if not exist "%FUTURE_AIRCRAFT_WS%" (
  echo [ERROR] FUTURE_AIRCRAFT_WS does not exist: %FUTURE_AIRCRAFT_WS%
  exit /b 1
)
if /I "%~1"=="--dry-run" (
  echo [DRY-RUN] Start MAVROS for /uav1 in WSL namespace
  echo [DRY-RUN] ROS_NAMESPACE=uav1, fcu_url:=udp://:14541@127.0.0.1:14581, tgt_system:=1
  exit /b 0
)
start "futureAircraftSim MAVROS uav1" wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "export ROS_NAMESPACE=uav1; source /opt/ros/noetic/setup.bash; source '%REF_28COM_UAV_WSL_DIR%/devel/setup.bash'; roslaunch mavros px4.launch fcu_url:=udp://:14541@127.0.0.1:14581 tgt_system:=1"
exit /b 0

