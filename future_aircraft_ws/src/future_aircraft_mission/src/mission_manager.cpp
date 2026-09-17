#include "future_aircraft_mission/mission_manager.hpp"

#include <cmath>


namespace
{

constexpr double kPi =
    3.14159265358979323846;


double degreesToRadians(
    double degrees)
{
    return degrees *
        kPi /
        180.0;
}


double distanceXY(
    const geometry_msgs::Point& a,
    const geometry_msgs::Point& b)
{
    const double dx =
        a.x - b.x;

    const double dy =
        a.y - b.y;


    return std::sqrt(
        dx * dx +
        dy * dy
    );
}

}  // namespace


MissionManager::MissionManager(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _uav1(
          nh,
          pnh,
          "uav1"),
      _uav2(
          nh,
          pnh,
          "uav2"),
      _mission_state(
          MissionState::WAIT_READY),
      _uav1_route_index(0),
      _uav2_route_index(0),
      _uav1_final_goal_sent(false),
      _uav2_final_goal_sent(false),
      _takeoff_altitude(1.0),
      _takeoff_yaw(0.0),
      _service_retry_s(1.0),
      _takeoff_tolerance_m(0.15),
      _landing_altitude_threshold_m(0.20),
      _planner_command_timeout_s(0.5),
      _goal_tolerance_m(0.30),
      _goal_settle_s(1.0),
      _ego_handoff_timeout_s(5.0),
      _entry_release_x(4.0),
      _smoke_test(false)
{
    pnh.param<bool>(
        "smoke_test",
        _smoke_test,
        false
    );


    pnh.param<double>(
        "entry_release_x",
        _entry_release_x,
        4.0
    );


    /*
     * Shared planning frame parameters.
     *
     * These MUST match SharedFrameAdapter and EgoSetpointBridge.
     */
    double uav1_origin_x = 0.0;
    double uav1_origin_y = -0.7;
    double uav1_origin_z = 0.0;
    double uav1_origin_yaw_deg = 0.0;

    double uav2_origin_x = 0.0;
    double uav2_origin_y = 0.7;
    double uav2_origin_z = 0.0;
    double uav2_origin_yaw_deg = 0.0;


    pnh.param<double>(
        "uav1_origin_x",
        uav1_origin_x,
        0.0
    );

    pnh.param<double>(
        "uav1_origin_y",
        uav1_origin_y,
        -0.7
    );

    pnh.param<double>(
        "uav1_origin_z",
        uav1_origin_z,
        0.0
    );

    pnh.param<double>(
        "uav1_origin_yaw_deg",
        uav1_origin_yaw_deg,
        0.0
    );


    pnh.param<double>(
        "uav2_origin_x",
        uav2_origin_x,
        0.0
    );

    pnh.param<double>(
        "uav2_origin_y",
        uav2_origin_y,
        0.7
    );

    pnh.param<double>(
        "uav2_origin_z",
        uav2_origin_z,
        0.0
    );

    pnh.param<double>(
        "uav2_origin_yaw_deg",
        uav2_origin_yaw_deg,
        0.0
    );


    _uav1_frame =
        PlanarFrameTransform(
            true,
            uav1_origin_x,
            uav1_origin_y,
            uav1_origin_z,
            degreesToRadians(
                uav1_origin_yaw_deg
            )
        );


    _uav2_frame =
        PlanarFrameTransform(
            true,
            uav2_origin_x,
            uav2_origin_y,
            uav2_origin_z,
            degreesToRadians(
                uav2_origin_yaw_deg
            )
        );


    buildCompetitionRoute();


    /*
     * planning_world:
     *
     * Competition ENU origin offset = (16, 0, 0)
     *
     * Pad 1 ENU = (32, 3.9)
     * Pad 2 ENU = (32, 5.9)
     *
     * therefore:
     *
     * Pad 1 planning_world = (16, 3.9)
     * Pad 2 planning_world = (16, 5.9)
     */
    _uav1_final_goal =
        RoutePoint(
            16.0,
            3.9,
            1.0,
            RoutePointType::LAND,
            0.30
        );


    _uav2_final_goal =
        RoutePoint(
            16.0,
            5.9,
            1.0,
            RoutePointType::LAND,
            0.30
        );
}


void MissionManager::buildCompetitionRoute()
{
    _route.clear();


    /*
     * All points are expressed in shared planning_world.
     *
     * Competition ENU:
     * planning_world origin = (16, 0, 0)
     *
     * These are intentionally SPARSE topology anchors.
     *
     * They are NOT precise trajectory checkpoints.
     */


    // P0: safely inside Section A.
    _route.emplace_back(
        3.4,
        0.0,
        1.0,
        RoutePointType::FLY_THROUGH,
        0.8
    );


    // P1: Section A, shortly before first bend.
    _route.emplace_back(
        6.5,
        0.0,
        1.0,
        RoutePointType::FLY_THROUGH,
        0.65
    );


    // P2: inside Section B, after first bend.
    _route.emplace_back(
        7.9,
        1.8,
        1.0,
        RoutePointType::FLY_THROUGH,
        0.8
    );


    // P3: Section B, before second bend.
    _route.emplace_back(
        7.9,
        3.6,
        1.0,
        RoutePointType::FLY_THROUGH,
        0.65
    );


    // P4: Section C, after second bend.
    _route.emplace_back(
        9.4,
        4.9,
        1.0,
        RoutePointType::FLY_THROUGH,
        0.8
    );


    // P5: tunnel exit.
    _route.emplace_back(
        14.0,
        4.9,
        1.0,
        RoutePointType::EXIT,
        0.4
    );
}


geometry_msgs::PoseStamped
MissionManager::makeLocalGoal(
    const RoutePoint& route_point,
    const PlanarFrameTransform& transform) const
{
    geometry_msgs::PoseStamped goal;


    goal.header.stamp =
        ros::Time::now();

    goal.header.frame_id =
        "uav_local";


    goal.pose.position =
        transform.worldToLocal(
            route_point.position
        );


    goal.pose.orientation.w =
        1.0;


    return goal;
}


geometry_msgs::Point
MissionManager::worldPosition(
    const UavAgent& uav,
    const PlanarFrameTransform& transform) const
{
    return transform.localToWorld(
        uav.position()
    );
}


bool MissionManager::shouldAdvanceRoutePoint(
    const geometry_msgs::Point& world_position,
    std::size_t route_index) const
{
    if (route_index >=
        _route.size()) {

        return false;
    }


    const RoutePoint& point =
        _route[route_index];


    /*
     * TASK points deliberately do NOT fly through.
     *
     * Later TaskManager will decide:
     *   - who claims it
     *   - when it is complete
     *   - when navigation may continue
     */
    if (point.type ==
        RoutePointType::TASK) {

        return false;
    }


    /*
     * Condition 1:
     * close enough to begin planning toward next topology anchor.
     */
    if (distanceXY(
            world_position,
            point.position) <=
        point.switch_radius) {

        return true;
    }


    /*
     * Condition 2:
     * already passed the waypoint plane.
     *
     * Avoids a UAV turning back simply because it passed slightly
     * outside the switch-radius circle.
     */
    geometry_msgs::Point tangent;


    if (route_index + 1 <
        _route.size()) {

        tangent.x =
            _route[route_index + 1].position.x -
            point.position.x;

        tangent.y =
            _route[route_index + 1].position.y -
            point.position.y;
    }
    else if (route_index > 0) {

        tangent.x =
            point.position.x -
            _route[route_index - 1].position.x;

        tangent.y =
            point.position.y -
            _route[route_index - 1].position.y;
    }
    else {

        return false;
    }


    const double relative_x =
        world_position.x -
        point.position.x;

    const double relative_y =
        world_position.y -
        point.position.y;


    const double dot =
        relative_x * tangent.x +
        relative_y * tangent.y;


    return dot > 0.0;
}


bool MissionManager::startRoute(
    UavAgent& uav,
    const PlanarFrameTransform& transform,
    std::size_t& route_index)
{
    if (_route.empty()) {
        return false;
    }


    route_index = 0;


    const geometry_msgs::PoseStamped goal =
        makeLocalGoal(
            _route.front(),
            transform
        );


    return uav.startNavigation(
        goal,
        _planner_command_timeout_s,
        _ego_handoff_timeout_s,
        _goal_tolerance_m,
        _goal_settle_s
    );
}


bool MissionManager::advanceRoute(
    UavAgent& uav,
    const PlanarFrameTransform& transform,
    std::size_t& route_index,
    const RoutePoint& final_goal,
    bool& final_goal_sent)
{
    if (uav.state() !=
        UavAgent::State::NAVIGATING) {

        return false;
    }


    if (route_index >=
        _route.size()) {

        return false;
    }


    if (uav.isNavigationHandoffPending()) {

        return false;
    }


    const RoutePoint& current_point =
        _route[route_index];


    /*
     * TASK is already part of the route representation,
     * but task semantics are intentionally not implemented yet.
     */
    if (current_point.type ==
        RoutePointType::TASK) {

        ROS_WARN_THROTTLE(
            5.0,
            "Reached TASK route point '%s', "
            "but TaskManager is not implemented yet",
            current_point.task_id.c_str()
        );

        return false;
    }


    const geometry_msgs::Point current_world_position =
        worldPosition(
            uav,
            transform
        );


    if (!shouldAdvanceRoutePoint(
            current_world_position,
            route_index)) {

        return false;
    }


    /*
     * There is another tunnel anchor.
     */
    if (route_index + 1 <
        _route.size()) {

        const std::size_t next_index =
            route_index + 1;


        const geometry_msgs::PoseStamped next_goal =
            makeLocalGoal(
                _route[next_index],
                transform
            );


        if (!uav.retargetNavigation(
                next_goal)) {

            return false;
        }


        route_index =
            next_index;


        ROS_INFO(
            "Route advanced to waypoint %zu",
            route_index
        );


        return true;
    }


    /*
     * Tunnel exit has been passed.
     * Switch directly to that UAV's own landing-area goal.
     */
    if (!final_goal_sent) {

        const geometry_msgs::PoseStamped landing_goal =
            makeLocalGoal(
                final_goal,
                transform
            );


        if (!uav.retargetNavigation(
                landing_goal)) {

            return false;
        }


        route_index =
            _route.size();


        final_goal_sent =
            true;


        ROS_INFO(
            "Tunnel route completed; "
            "retargeting to final landing goal"
        );


        return true;
    }


    return false;
}


void MissionManager::tick()
{
    _uav1.tick();

    _uav2.tick();


    switch (_mission_state)
    {

    case MissionState::WAIT_READY:
    {
        const bool ready =
            _smoke_test
            ? (
                _uav1.isVehicleReady() &&
                _uav2.isVehicleReady()
              )
            : (
                _uav1.isReady() &&
                _uav2.isReady()
              );


        const bool both_idle =
            _uav1.state() ==
                UavAgent::State::IDLE &&
            _uav2.state() ==
                UavAgent::State::IDLE;


        if (!ready ||
            !both_idle) {

            break;
        }


        const bool uav1_started =
            _uav1.startTakeoff(
                _takeoff_altitude,
                _takeoff_yaw,
                _takeoff_tolerance_m
            );


        const bool uav2_started =
            _uav2.startTakeoff(
                _takeoff_altitude,
                _takeoff_yaw,
                _takeoff_tolerance_m
            );


        if (uav1_started &&
            uav2_started) {

            transitionTo(
                MissionState::TAKEOFF
            );
        }


        break;
    }


    case MissionState::TAKEOFF:
    {
        const bool both_holding =
            _uav1.state() ==
                UavAgent::State::HOLDING &&
            _uav2.state() ==
                UavAgent::State::HOLDING;


        if (!both_holding) {
            break;
        }


        if (_smoke_test) {

            transitionTo(
                MissionState::AUTO_LAND
            );
        }
        else {

            transitionTo(
                MissionState::START_UAV1_ROUTE
            );
        }


        break;
    }


    case MissionState::START_UAV1_ROUTE:
    {
        if (startRoute(
                _uav1,
                _uav1_frame,
                _uav1_route_index)) {

            ROS_INFO(
                "UAV1 released toward tunnel entry"
            );


            transitionTo(
                MissionState::WAIT_UAV1_ENTRY
            );
        }


        break;
    }


    case MissionState::WAIT_UAV1_ENTRY:
    {
        if (_uav1.state() ==
            UavAgent::State::ERROR) {

            ROS_ERROR(
                "UAV1 failed during tunnel entry"
            );


            transitionTo(
                MissionState::AUTO_LAND
            );


            break;
        }


        /*
         * UAV1 continues following / retargeting its route
         * while UAV2 waits at the takeoff hold point.
         */
        advanceRoute(
            _uav1,
            _uav1_frame,
            _uav1_route_index,
            _uav1_final_goal,
            _uav1_final_goal_sent
        );


        const geometry_msgs::Point uav1_world =
            worldPosition(
                _uav1,
                _uav1_frame
            );


        /*
         * Release follower only after leader is well inside Section A.
         */
        if (uav1_world.x <
            _entry_release_x) {

            break;
        }


        if (startRoute(
                _uav2,
                _uav2_frame,
                _uav2_route_index)) {

            ROS_INFO(
                "UAV2 released after UAV1 entered tunnel"
            );


            transitionTo(
                MissionState::TRAVERSE_ROUTE
            );
        }


        break;
    }


    case MissionState::TRAVERSE_ROUTE:
    {
        /*
         * Once both vehicles are inside, they progress independently.
         *
         * There is NO waypoint-by-waypoint synchronization.
         *
         * Inter-UAV avoidance remains EGO-Swarm's responsibility.
         */
        advanceRoute(
            _uav1,
            _uav1_frame,
            _uav1_route_index,
            _uav1_final_goal,
            _uav1_final_goal_sent
        );


        advanceRoute(
            _uav2,
            _uav2_frame,
            _uav2_route_index,
            _uav2_final_goal,
            _uav2_final_goal_sent
        );


        if (_uav1.state() ==
                UavAgent::State::ERROR ||
            _uav2.state() ==
                UavAgent::State::ERROR) {

            ROS_ERROR(
                "Tunnel traversal failed"
            );


            transitionTo(
                MissionState::AUTO_LAND
            );


            break;
        }


        if (_uav1_final_goal_sent &&
            _uav2_final_goal_sent) {

            transitionTo(
                MissionState::WAIT_FINAL_REACHED
            );
        }


        break;
    }


    case MissionState::WAIT_FINAL_REACHED:
    {
        const bool uav1_done =
            _uav1.state() ==
                UavAgent::State::HOLDING ||
            _uav1.state() ==
                UavAgent::State::ERROR;


        const bool uav2_done =
            _uav2.state() ==
                UavAgent::State::HOLDING ||
            _uav2.state() ==
                UavAgent::State::ERROR;


        if (uav1_done &&
            uav2_done) {

            transitionTo(
                MissionState::AUTO_LAND
            );
        }


        break;
    }


    case MissionState::AUTO_LAND:
    {
        const auto state1 =
            _uav1.state();

        const auto state2 =
            _uav2.state();


        if (state1 ==
                UavAgent::State::HOLDING ||
            state1 ==
                UavAgent::State::ERROR) {

            _uav1.startLanding(
                _landing_altitude_threshold_m,
                _service_retry_s,
                _takeoff_yaw
            );
        }


        if (state2 ==
                UavAgent::State::HOLDING ||
            state2 ==
                UavAgent::State::ERROR) {

            _uav2.startLanding(
                _landing_altitude_threshold_m,
                _service_retry_s,
                _takeoff_yaw
            );
        }


        if (_uav1.state() ==
                UavAgent::State::FINISHED &&
            _uav2.state() ==
                UavAgent::State::FINISHED) {

            transitionTo(
                MissionState::FINISHED
            );
        }


        break;
    }


    case MissionState::FINISHED:
    {
        break;
    }

    }
}


void MissionManager::transitionTo(
    MissionState next_state)
{
    ROS_INFO(
        "Mission state changed: %d -> %d",
        static_cast<int>(_mission_state),
        static_cast<int>(next_state)
    );


    _mission_state =
        next_state;
}


MissionManager::MissionState
MissionManager::state() const
{
    return _mission_state;
}