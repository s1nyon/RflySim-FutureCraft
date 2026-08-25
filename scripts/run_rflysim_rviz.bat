@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%..\config\env_template.bat"
if exist "%SCRIPT_DIR%..\config\env_local.bat" call "%SCRIPT_DIR%..\config\env_local.bat"

set "RVIZ_MODE=%~1"
set "DRY_RUN=0"
if not defined RVIZ_MODE set "RVIZ_MODE=dual"
if /I "%RVIZ_MODE%"=="--dry-run" (
  set "RVIZ_MODE=dual"
  set "DRY_RUN=1"
)
if /I "%~2"=="--dry-run" set "DRY_RUN=1"

if /I not "%RVIZ_MODE%"=="uav1" if /I not "%RVIZ_MODE%"=="uav2" if /I not "%RVIZ_MODE%"=="dual" (
  echo [ERROR] RViz mode must be uav1, uav2, or dual: %RVIZ_MODE%
  exit /b 2
)

if "%DRY_RUN%"=="1" (
  echo [DRY-RUN] Project RViz mode=%RVIZ_MODE%
  echo [DRY-RUN] X11 readiness: DISPLAY=127.0.0.1:0.0 xdpyinfo
  echo [DRY-RUN] ROS launch: multi_uav_mission rflysim_rviz.launch rviz_mode:=%RVIZ_MODE%
  exit /b 0
)

wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lc "source /opt/ros/noetic/setup.bash; source '%REF_28COM_UAV_WSL_DIR%/devel/setup.bash'; source '%EGO_SWARM_WSL_DIR%/devel/setup.bash'; source '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/future_aircraft_ws/devel/setup.bash'; export ROS_MASTER_URI='http://localhost:11311'; export DISPLAY='127.0.0.1:0.0'; export LIBGL_ALWAYS_INDIRECT=0; if ! timeout 5s xdpyinfo >/dev/null 2>&1; then echo '[ERROR] VcXsrv display 127.0.0.1:0.0 is not ready' >&2; exit 20; fi; exec roslaunch multi_uav_mission rflysim_rviz.launch rviz_mode:='%RVIZ_MODE%'"
exit /b %ERRORLEVEL%
