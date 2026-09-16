#pragma once

#include <ros/ros.h>
#include <geometry_msgs/PoseStamped.h>

#include "future_aircraft_mission/uav_agent.hpp"

class MissionManager
{
public:
    enum class MissionState
    {
        WAIT_READY,
        TAKEOFF,
        SEND_UAV1_GOAL,
        WAIT_UAV1_TRAJECTORY,
        SEND_UAV2_GOAL,
        WAIT_REACHED,
        AUTO_LAND,
        FINISHED
    };

    MissionManager(ros::NodeHandle& nh, ros::NodeHandle& pnh);

    void tick();

    MissionState state() const;

private:
    void transitionTo(MissionState next_state);

    UavAgent _uav1;
    UavAgent _uav2;
    MissionState _mission_state;

    double _takeoff_altitude;
    double _takeoff_yaw;
    double _service_retry_s;
    double _takeoff_tolerance_m;
    double _landing_altitude_threshold_m;

    double _uav1_goal_x;
    double _uav1_goal_y;
    double _uav1_goal_z;
    double _uav2_goal_x;
    double _uav2_goal_y;
    double _uav2_goal_z;

    double _planner_command_timeout_s;

    bool _smoke_test; // smoke_test contains takeoff -> land

    double _goal_tolerance_m;
    double _goal_settle_s;

    double _ego_handoff_timeout_s;
};