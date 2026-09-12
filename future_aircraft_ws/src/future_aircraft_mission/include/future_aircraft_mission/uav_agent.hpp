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

    enum class State
    {
        IDLE,
        TAKING_OFF,
        HOLDING,
        NAVIGATING,
        LANDING,
        FINISHED
    };

    void gotoGoal(const geometry_msgs::PoseStamped& goal);
    bool hasReachedGoal(double tolerance_m) const;
    bool requestOffboard();
    bool arm();
    bool land();
    bool disarm();

    bool isArmed() const;
    bool isOffboard() const;
    bool isAutoLand() const;
    bool isVehicleReady() const;
    bool isReady() const;

    void publishTakeoffSetpoint(
        double altitude_m,
        double yaw
    );

    bool hasReachedTakeoffAltitude(
        double altitude_m,
        double tolerance_m
    ) const;

    bool isNearGround(double threshold_m) const;

    bool hasPlannerCommand() const;
    bool isPlannerCommandFresh(double timeout_s) const;

    void publishCurrentPositionHold(double yaw);

    State state() const;

    bool startTakeoff(double altitude_m, double yaw, double tolerance_m);

    void tick();


private:

    void transitionTo(State next_state);
    bool hasFinishedTakeoff() const;

    std::string _uav_name;
    ros::NodeHandle _nh;
    ros::NodeHandle _pnh;
    VehicleInterface _vehicle;
    EgoInterface _ego;
    State _state;

    double _takeoff_altitude;
    double _takeoff_yaw;
    double _takeoff_tolerance_m;

    ros::Time _takeoff_start_time;
    ros::Time _last_offboard_request_time;
    ros::Time _last_arm_request_time;
};