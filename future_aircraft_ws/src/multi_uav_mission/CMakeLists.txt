cmake_minimum_required(VERSION 3.0.2)
project(multi_uav_mission)

find_package(catkin REQUIRED)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/behavior_tree_runner.py
  scripts/ego_swarm_adapter.py
  scripts/ego_swarm_flight_smoke_check.py
  scripts/ego_swarm_setpoint_bridge.py
  scripts/live_mission_contract.py
  scripts/live_smoke_runbook.py
  scripts/mavlink_return_path_check.py
  scripts/mavros_smoke_check.py
  scripts/mavros_setpoint_keepalive.py
  scripts/mission_executor.py
  scripts/odom_frame_relay.py
  scripts/rflysim_cloud_contract.py
  scripts/rflysim_pointcloud_adapter.py
  scripts/rflysim_sensor_bridge.py
  scripts/score_summary.py
  scripts/sim_vision_target_provider.py
  scripts/stage7_flight_plan.py
  scripts/stage7_flight_report.py
  scripts/stage7_run_artifacts.py
  scripts/stage7_sensor_readiness.py
  scripts/stage7_topic_probe.py
  scripts/target_provider.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
