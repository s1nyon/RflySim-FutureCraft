#pragma once

#include <ros/ros.h>
#include <geometry_msgs/PoseStamped.h>

#include "future_aircraft_mission/uav_agent.hpp"

class MissionManager
{
public:
    enum class State
    {
        WAIT_READY,
        TAKEOFF,
        SEND_EGO_GOAL,
        WAIT_REACHED,
        AUTO_LAND,
        DISARM,
        FINISHED
    };

    MissionManager(ros::NodeHandle& nh, ros::NodeHandle& pnh);

    void tick();

    State state() const;

private:
    void transitionTo(State next_state);

    UavAgent _uav;
    State _state;

    ros::Time _state_enter_time;
    ros::Time _last_offboard_request_time;
    ros::Time _last_arm_request_time;
    ros::Time _last_land_request_time;
    ros::Time _last_disarm_request_time;

    double _takeoff_altitude;
    double _takeoff_yaw;
    double _offboard_warmup_s;
    double _service_retry_s;
    double _takeoff_tolerance_m;
    double _landing_altitude_threshold_m;

    double _goal_x;
    double _goal_y;
    double _goal_z;

    double _planner_command_timeout_s;

    bool _ego_goal_sent;

    bool _smoke_test; // smoke_test contains takeoff -> land
};