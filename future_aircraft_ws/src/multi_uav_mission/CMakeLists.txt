cmake_minimum_required(VERSION 3.0.2)
project(multi_uav_mission)

find_package(catkin REQUIRED)

catkin_package()

catkin_install_python(PROGRAMS
  scripts/ego_swarm_adapter.py
  scripts/score_summary.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

