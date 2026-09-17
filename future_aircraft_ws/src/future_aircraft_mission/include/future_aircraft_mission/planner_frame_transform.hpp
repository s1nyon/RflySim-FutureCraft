#pragma once

#include <cmath>

#include <geometry_msgs/Point.h>
#include <geometry_msgs/Quaternion.h>
#include <geometry_msgs/Vector3.h>

#include <tf2/LinearMath/Quaternion.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.h>

class PlanarFrameTransform
{
public:
    PlanarFrameTransform()
        : _enabled(false),
          _origin_x(0.0),
          _origin_y(0.0),
          _origin_z(0.0),
          _origin_yaw_rad(0.0)
    {
    }

    PlanarFrameTransform(
        bool enabled,
        double origin_x,
        double origin_y,
        double origin_z,
        double origin_yaw_rad)
        : _enabled(enabled),
          _origin_x(origin_x),
          _origin_y(origin_y),
          _origin_z(origin_z),
          _origin_yaw_rad(origin_yaw_rad)
    {
    }

    geometry_msgs::Point localToWorld(
        const geometry_msgs::Point& local) const
    {
        if (!_enabled) {
            return local;
        }

        const double c = std::cos(_origin_yaw_rad);
        const double s = std::sin(_origin_yaw_rad);

        geometry_msgs::Point world;

        world.x =
            _origin_x +
            c * local.x -
            s * local.y;

        world.y =
            _origin_y +
            s * local.x +
            c * local.y;

        world.z =
            _origin_z +
            local.z;

        return world;
    }

    geometry_msgs::Point worldToLocal(
        const geometry_msgs::Point& world) const
    {
        if (!_enabled) {
            return world;
        }

        const double c = std::cos(_origin_yaw_rad);
        const double s = std::sin(_origin_yaw_rad);

        const double dx = world.x - _origin_x;
        const double dy = world.y - _origin_y;

        geometry_msgs::Point local;

        local.x =
            c * dx +
            s * dy;

        local.y =
            -s * dx +
            c * dy;

        local.z =
            world.z -
            _origin_z;

        return local;
    }

    geometry_msgs::Vector3 localToWorldVector(
        const geometry_msgs::Vector3& local) const
    {
        if (!_enabled) {
            return local;
        }

        const double c = std::cos(_origin_yaw_rad);
        const double s = std::sin(_origin_yaw_rad);

        geometry_msgs::Vector3 world;

        world.x =
            c * local.x -
            s * local.y;

        world.y =
            s * local.x +
            c * local.y;

        world.z = local.z;

        return world;
    }

    geometry_msgs::Quaternion localToWorldOrientation(
        const geometry_msgs::Quaternion& local) const
    {
        if (!_enabled) {
            return local;
        }

        tf2::Quaternion q_world_local;
        q_world_local.setRPY(
            0.0,
            0.0,
            _origin_yaw_rad
        );

        tf2::Quaternion q_local_body;
        tf2::fromMsg(local, q_local_body);

        tf2::Quaternion q_world_body =
            q_world_local *
            q_local_body;

        q_world_body.normalize();

        return tf2::toMsg(q_world_body);
    }

    double worldToLocalYaw(
        double world_yaw) const
    {
        if (!_enabled) {
            return world_yaw;
        }

        return normalizeAngle(
            world_yaw -
            _origin_yaw_rad
        );
    }

    bool enabled() const
    {
        return _enabled;
    }

private:
    static double normalizeAngle(double angle)
    {
        return std::atan2(
            std::sin(angle),
            std::cos(angle)
        );
    }

private:
    bool _enabled;

    double _origin_x;
    double _origin_y;
    double _origin_z;

    double _origin_yaw_rad;
};