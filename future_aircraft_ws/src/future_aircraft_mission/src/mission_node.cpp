#include <ros/ros.h>

#include "future_aircraft_mission/mission_manager.hpp"

int main(int argc, char** argv)
{
    ros::init(argc, argv, "future_aircraft_mission");

    ros::NodeHandle nh;
    ros::NodeHandle pnh("~");

    MissionManager mission(nh, pnh);

    ros::Rate rate(20.0);

    while (ros::ok())
    {
        ros::spinOnce();

        mission.tick();

        rate.sleep();
    }

    return 0;
}