#pragma once

#include <ros/ros.h>

#include <geometry_msgs/PoseStamped.h>

#include <cstddef>
#include <vector>


#include "future_aircraft_mission/uav_agent.hpp"
#include "future_aircraft_mission/route_point.hpp"
#include "future_aircraft_mission/planar_frame_transform.hpp"


class MissionManager
{
public:
    enum class MissionState
    {
        WAIT_READY,
        TAKEOFF,

        START_UAV1_ROUTE,

        WAIT_UAV1_ENTRY,

        TRAVERSE_ROUTE,

        WAIT_FINAL_REACHED,

        AUTO_LAND,

        FINISHED
    };


    MissionManager(
        ros::NodeHandle& nh,
        ros::NodeHandle& pnh
    );


    void tick();


    MissionState state() const;


private:
    void transitionTo(
        MissionState next_state
    );


    void buildCompetitionRoute();


    geometry_msgs::PoseStamped makeLocalGoal(
        const RoutePoint& route_point,
        const PlanarFrameTransform& transform
    ) const;


    geometry_msgs::Point worldPosition(
        const UavAgent& uav,
        const PlanarFrameTransform& transform
    ) const;


    bool shouldAdvanceRoutePoint(
        const geometry_msgs::Point& world_position,
        std::size_t route_index
    ) const;


    bool advanceRoute(
        UavAgent& uav,
        const PlanarFrameTransform& transform,
        std::size_t& route_index,
        const RoutePoint& final_goal,
        bool& final_goal_sent
    );


    bool startRoute(
        UavAgent& uav,
        const PlanarFrameTransform& transform,
        std::size_t& route_index
    );


private:
    UavAgent _uav1;

    UavAgent _uav2;


    MissionState _mission_state;


    std::vector<RoutePoint> _route;


    std::size_t _uav1_route_index;

    std::size_t _uav2_route_index;


    bool _uav1_final_goal_sent;

    bool _uav2_final_goal_sent;


    RoutePoint _uav1_final_goal;

    RoutePoint _uav2_final_goal;


    PlanarFrameTransform _uav1_frame;

    PlanarFrameTransform _uav2_frame;


    double _takeoff_altitude;

    double _takeoff_yaw;

    double _service_retry_s;

    double _takeoff_tolerance_m;

    double _landing_altitude_threshold_m;


    double _planner_command_timeout_s;

    double _goal_tolerance_m;

    double _goal_settle_s;

    double _ego_handoff_timeout_s;


    /*
     * UAV2 is released only after UAV1 has moved sufficiently
     * inside Section A.
     *
     * planning_world x coordinate.
     */
    double _entry_release_x;


    bool _smoke_test;
};