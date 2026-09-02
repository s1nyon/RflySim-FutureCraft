#pragma once

// VehicleInterface: thin, owned wrapper over MAVROS state/mode/arming for one UAV.
// Skeleton for the human-led C++ competition mission; review before implementation.

#include <ros/ros.h>
#include <mavros_msgs/State.h>

#include <string>

namespace future_aircraft_mission
{

class VehicleInterface
{
public:
  struct State
  {
    bool connected = false;
    bool armed = false;
    std::string mode;
  };

  explicit VehicleInterface(ros::NodeHandle & nh, const std::string & uav_namespace);

  // Latest observed MAVROS state (subscriber cache).
  State state() const;

  // True when connected and NOT armed and mode != OFFBOARD (WAIT_READY gate).
  bool readyForMission() const;

  // Mode/OFFBOARD request. Returns service success.
  bool requestOffboard();

  // Arm request (simulation gate responsibility stays outside this class).
  bool arm();
  bool disarm();

  // True if the caller may arm under the current simulation policy.
  bool simulationArmAllowed() const;

private:
  void stateCallback(const mavros_msgs::State::ConstPtr & message);

  ros::NodeHandle nh_;
  std::string ns_;
  std::string state_topic_;
  std::string set_mode_service_;
  std::string arming_service_;

  ros::Subscriber state_sub_;
  ros::ServiceClient set_mode_client_;
  ros::ServiceClient arming_client_;

  State state_;
  bool simulation_arm_allowed_ = false;
};

}  // namespace future_aircraft_mission
