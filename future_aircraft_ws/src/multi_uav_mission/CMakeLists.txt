cmake_minimum_required(VERSION 3.0.2)
project(multi_uav_mission)

find_package(catkin REQUIRED)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/behavior_tree_runner.py
  scripts/ego_swarm_adapter.py
  scripts/live_mission_contract.py
  scripts/live_smoke_runbook.py
  scripts/mavlink_return_path_check.py
  scripts/mavros_smoke_check.py
  scripts/mission_executor.py
  scripts/score_summary.py
  scripts/sim_vision_target_provider.py
  scripts/target_provider.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
