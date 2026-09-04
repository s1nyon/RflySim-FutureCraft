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

    void gotoGoal(const geometry_msgs::PoseStamped& goal);
    bool hasReachedGoal(double tolerance_m) const;
    bool requestOffboard();
    bool arm();
    bool land();
    bool disarm();

    bool isArmed() const;
    bool isOffboard() const;
    bool isReady() const;

private:
    std::string _uav_name;

    ros::NodeHandle _nh;
    ros::NodeHandle _pnh;

    VehicleInterface _vehicle;
    EgoInterface _ego;
};