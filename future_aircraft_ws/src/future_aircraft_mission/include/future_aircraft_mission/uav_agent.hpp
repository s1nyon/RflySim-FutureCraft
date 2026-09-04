#pragma once

#include <ros/ros.h>
#include <string>

#include "future_aircraft_mission/vehicle_interface.hpp"
#include "future_aircraft_mission/ego_interface.hpp"

class UavAgent
{
public:
    UavAgent(
        ros::NodeHandle& nh,
        ros::NodeHandle& pnh,
        const std::string& uav_name
    );

    bool isReady() const;

    void gotoGoal(const geometry_msgs::PoseStamped& goal);

    bool hasReachedGoal(double tolerance_m) const;

private:
    std::string _uav_name;

    ros::NodeHandle _nh;
    ros::NodeHandle _pnh;

    VehicleInterface _vehicle;
    EgoInterface _ego;
};