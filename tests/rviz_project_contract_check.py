#!/usr/bin/env python3
"""Offline contract checks for standalone truthful per-UAV RViz."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def parameters(node):
    return {item.attrib["name"]: item.attrib.get("value") for item in node.findall("param")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    package = root / "future_aircraft_ws" / "src" / "multi_uav_mission"
    launch_path = package / "launch" / "rflysim_rviz.launch"
    launch = ET.parse(str(launch_path)).getroot()

    mode = next(item for item in launch.findall("arg") if item.attrib.get("name") == "rviz_mode")
    assert mode.attrib.get("default") == "dual"
    validation = next(
        item for item in launch.findall("arg") if item.attrib.get("name") == "validated_mode"
    )
    validation_text = validation.attrib.get("default", "")
    for accepted in ("uav1", "uav2", "dual"):
        assert accepted in validation_text

    all_nodes = launch.findall(".//node")
    rviz_nodes = [item for item in all_nodes if item.attrib.get("pkg") == "rviz"]
    adapter_nodes = [
        item for item in all_nodes if item.attrib.get("type") == "rviz_frame_adapter.py"
    ]
    assert len(rviz_nodes) == 2
    assert len(adapter_nodes) == 2
    assert len({item.attrib["name"] for item in rviz_nodes}) == 2
    assert not any(item.attrib.get("type") == "static_transform_publisher" for item in all_nodes)

    expected = {
        "uav1": {
            "frame_id": "uav1_camera_init",
            "odom_topic": "/uav1/mavros/odometry/out",
            "path_topic": "/uav1/viz/path",
            "optimal_marker_topic": "/uav1/planner/rflysim_ego_swarm_node/optimal_list",
            "optimal_marker_output_topic": "/uav1/viz/optimal_trajectory",
            "goal_marker_topic": "/uav1/planner/rflysim_ego_swarm_node/goal_point",
            "goal_marker_output_topic": "/uav1/viz/goal",
            "position_command_topic": "/uav1/planning/pos_cmd",
            "position_command_output_topic": "/uav1/viz/position_command",
        },
        "uav2": {
            "frame_id": "uav2_camera_init",
            "odom_topic": "/uav2/mavros/odometry/out",
            "path_topic": "/uav2/viz/path",
            "optimal_marker_topic": "/uav2/planner/rflysim_ego_swarm_node/optimal_list",
            "optimal_marker_output_topic": "/uav2/viz/optimal_trajectory",
            "goal_marker_topic": "/uav2/planner/rflysim_ego_swarm_node/goal_point",
            "goal_marker_output_topic": "/uav2/viz/goal",
            "position_command_topic": "/uav2/planning/pos_cmd",
            "position_command_output_topic": "/uav2/viz/position_command",
        },
    }
    for uav, contract in expected.items():
        adapter = next(item for item in adapter_nodes if uav in item.attrib["name"])
        adapter_parameters = parameters(adapter)
        assert all(adapter_parameters.get(name) == value for name, value in contract.items())
        assert adapter_parameters["max_path_poses"] == "600"

        config = package / "rviz" / "future_aircraft_{}.rviz".format(uav)
        text = config.read_text(encoding="utf-8")
        assert "Fixed Frame: {}_camera_init".format(uav) in text
        assert "Frame Rate: 10" in text
        for topic in (
            "/{}/mavros/odometry/out".format(uav),
            "/{}/viz/path".format(uav),
            "/{}/rflysim/lidar".format(uav),
            "/{}/viz/optimal_trajectory".format(uav),
            "/{}/viz/goal".format(uav),
            "/{}/viz/position_command".format(uav),
        ):
            assert "Topic: {}".format(topic) in text
        # Raw LiDAR remains available for on-demand inspection, but two live
        # PointCloud2 renderers saturated more than one CPU core in the
        # dual-window live run.  Keep the expensive display off by default so
        # enabling RViz cannot silently perturb the protected flight path.
        lidar_block = text.split("Name: LiDAR (sensor frame)", 1)[0].rsplit(
            "- Class: rviz/PointCloud2", 1
        )[-1]
        assert "Enabled: false" in lidar_block
        other = "uav2" if uav == "uav1" else "uav1"
        assert "/{}/".format(other) not in text
        assert "competition_world" not in text

    fastlio = ET.parse(str(package / "launch" / "rflysim_fastlio_dual.launch")).getroot()
    rviz_arg = next(item for item in fastlio.findall("arg") if item.attrib.get("name") == "rviz")
    assert rviz_arg.attrib.get("default") == "false"
    assert not any(
        "rflysim_rviz.launch" in item.attrib.get("file", "") for item in fastlio.findall(".//include")
    )

    package_manifest = ET.parse(str(package / "package.xml")).getroot()
    runtime_dependencies = {
        item.text.strip() for item in package_manifest.findall("exec_depend") if item.text
    }
    assert {
        "nav_msgs",
        "quadrotor_msgs",
        "rospy",
        "rviz",
        "visualization_msgs",
    }.issubset(runtime_dependencies)

    windows_launcher = root / "scripts" / "run_rflysim_rviz.bat"
    launcher_text = windows_launcher.read_text(encoding="utf-8").lower()
    assert "127.0.0.1:0.0" in launcher_text
    assert "xdpyinfo" in launcher_text
    assert "rviz_mode:=" in launcher_text
    # A live RViz session must be attached to the current lifecycle manifest at
    # creation time. Otherwise stack inspection correctly classifies roslaunch
    # and its children as unknown and refuses any simulation arming.
    assert "--stack-id" in launcher_text
    assert "--manifest" in launcher_text
    assert "stack_manifest_wsl" in launcher_text
    assert "rviz_live.sh" in launcher_text
    assert "rfly_stack_id=" in launcher_text

    wsl_launcher = root / "scripts" / "wsl" / "rviz_live.sh"
    wsl_launcher_text = wsl_launcher.read_text(encoding="utf-8").lower()
    assert "lifecycle_common.sh" in wsl_launcher_text
    assert "stack_register wsl" in wsl_launcher_text
    assert "wsl:rviz_session" in wsl_launcher_text
    assert "exec roslaunch" in wsl_launcher_text
    assert "set -euo pipefail" not in wsl_launcher_text
    assert wsl_launcher_text.index("source /opt/ros/noetic/setup.bash") < wsl_launcher_text.index(
        "set -u"
    )
    for mode_name in ("uav1", "uav2", "dual"):
        assert mode_name in launcher_text
    assert "static_transform_publisher" not in launcher_text
    assert "competition_world" not in launcher_text

    print("project RViz contract checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
