cmake_minimum_required(VERSION 3.0.2)
project(future_aircraft_mission)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  quadrotor_msgs
  mavros_msgs
)

catkin_package(
  INCLUDE_DIRS include
  LIBRARIES future_aircraft_mission
  CATKIN_DEPENDS roscpp quadrotor_msgs mavros_msgs
)

include_directories(include ${catkin_INCLUDE_DIRS})

add_library(future_aircraft_mission src/ego_setpoint_bridge.cpp)
add_executable(ego_setpoint_bridge_node src/ego_setpoint_bridge_node.cpp)
add_dependencies(future_aircraft_mission ${catkin_EXPORTED_TARGETS})
add_dependencies(ego_setpoint_bridge_node ${catkin_EXPORTED_TARGETS})
target_link_libraries(future_aircraft_mission ${catkin_LIBRARIES})
target_link_libraries(ego_setpoint_bridge_node future_aircraft_mission ${catkin_LIBRARIES})
