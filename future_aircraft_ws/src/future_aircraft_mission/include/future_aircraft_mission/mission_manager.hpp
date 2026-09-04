#pragma once

#include <ros/ros.h>

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

    double _takeoff_altitude;
    double _takeoff_yaw;
    double _offboard_warmup_s;
    double _service_retry_s;
    double _takeoff_tolerance_m;
};