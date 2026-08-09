#include <ros/ros.h>
#include "future_aircraft_mission/ego_setpoint_bridge.hpp"

int main(int argc, char** argv)
{
    ros::init(argc, argv, "ego_setpoint_bridge");

    ros::NodeHandle nh;
    ros::NodeHandle pnh("~");

    ros::spin();

    return 0;
}