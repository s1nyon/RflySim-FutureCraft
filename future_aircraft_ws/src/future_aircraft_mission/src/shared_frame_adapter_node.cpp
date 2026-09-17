#include <ros/ros.h>

#include "future_aircraft_mission/shared_frame_adapter.hpp"

int main(int argc, char** argv)
{
    ros::init(
        argc,
        argv,
        "shared_frame_adapter"
    );

    ros::NodeHandle nh;
    ros::NodeHandle pnh("~");

    SharedFrameAdapter adapter(
        nh,
        pnh
    );

    ros::spin();

    return 0;
}