#pragma once

// EgoInterface: publishes one EGO goal and reads planner evidence for one UAV.
// Skeleton for the human-led C++ competition mission; review before implementation.

#include <geometry_msgs/PoseStamped.h>
#include <ros/ros.h>

#include <string>

namespace future_aircraft_mission
{

class EgoInterface
{
public:
  explicit EgoInterface(ros::NodeHandle & nh, const std::string & uav_namespace);

  // Publish one terminal goal in the verified local ENU frame (frame_id "map").
  // position_xyz uses the same numeric local coordinates as the frozen V2 plan.
  void sendGoal(double x, double y, double z, double yaw = 0.0);

  // Latest planner command count observed since construction (evidence).
  std::size_t plannerCommandCount() const;

private:
  ros::NodeHandle nh_;
  std::string goal_topic_;
  std::string planner_command_topic_;

  ros::Publisher goal_pub_;
  ros::Subscriber planner_command_sub_;

  std::size_t planner_command_count_ = 0;
};

}  // namespace future_aircraft_mission
