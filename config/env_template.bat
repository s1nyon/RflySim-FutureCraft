@echo off
rem Copy this file to env_local.bat if machine-specific values are needed.
for %%I in ("%~dp0..") do set FUTURE_AIRCRAFT_SIM_DIR=%%~fI
set RFLYSIM_ROOT=D:\PX4PSP
set PSP_PATH=D:\PX4PSP
set PSP_PATH_LINUX=/mnt/d/PX4PSP
set RFLYSIM_WSL_DISTRO=RflySim-20.04
set RFLYSIM_UAV_SITL_SCRIPT=%RFLYSIM_ROOT%\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\28com_sim\28com_SITL\UAVSITL.bat
set RFLYSIM_VCXSRV_DIR=%RFLYSIM_ROOT%\VcXsrv
set REF_28COM_UAV_DIR=%RFLYSIM_ROOT%\RflySimAPIs\8.RflySimVision\3.CustExps\e13.RobotCom26Adv\28com_sim\UAV_demo\28com_uav
set REF_28COM_UAV_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/28com_sim/UAV_demo/28com_uav
set EGO_SWARM_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/external/ego-planner-swarm
set FUTURE_AIRCRAFT_WS=%FUTURE_AIRCRAFT_SIM_DIR%\future_aircraft_ws
set FUTURE_AIRCRAFT_SIM_WSL_DIR=/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim
set ROS_MASTER_URI=http://127.0.0.1:11311
set ROS_IP=127.0.0.1
set ROS_DISTRO=noetic
set SIM_AUTO_ARM=1
set STAGE1_BOOT_WAIT_SECONDS=20


rem Keep both UAVs inside the ChallengeMap origin area while avoiding overlap.
if not defined STAGE2_POS_X_STR set STAGE2_POS_X_STR=0.5,1.5
if not defined STAGE2_POS_Y_STR set STAGE2_POS_Y_STR=1.5,1.5
if not defined STAGE2_YAW_STR set STAGE2_YAW_STR=0,0
set STAGE2_BOOT_WAIT_SECONDS=30

if not defined RFLYSIM_UE4_MAP set RFLYSIM_UE4_MAP=ChallengeMap
if not defined PREDICTED_COURSE_BASE_MAP set PREDICTED_COURSE_BASE_MAP=VisionRingBlank
if not defined PREDICTED_COURSE_POS_X_STR set PREDICTED_COURSE_POS_X_STR=-0.7,0.7
if not defined PREDICTED_COURSE_POS_Y_STR set PREDICTED_COURSE_POS_Y_STR=0,0
if not defined PREDICTED_COURSE_YAW_STR set PREDICTED_COURSE_YAW_STR=90,90

set PYTHON_EXE=%RFLYSIM_ROOT%\Python38\python.exe

