#pragma once

#include <geometry_msgs/Point.h>

#include <string>


enum class RoutePointType
{
    FLY_THROUGH,
    TASK,
    EXIT,
    LAND
};


struct RoutePoint
{
    geometry_msgs::Point position;

    RoutePointType type;

    double switch_radius;

    std::string task_id;


    RoutePoint()
        : type(RoutePointType::FLY_THROUGH),
          switch_radius(1.0)
    {
    }


    RoutePoint(
        double x,
        double y,
        double z,
        RoutePointType point_type,
        double radius,
        const std::string& task = "")
        : type(point_type),
          switch_radius(radius),
          task_id(task)
    {
        position.x = x;
        position.y = y;
        position.z = z;
    }
};