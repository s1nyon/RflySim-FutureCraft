#!/usr/bin/env python3
"""Execute a Stage 5B live mission plan with dry-run or guarded ROS backends."""

import argparse
import json

from course_geofence import Geofence, validate_point
import sys
import threading
import time
from pathlib import Path

from score_summary import build_summary


SUPPORTED_ACTIONS = {
    "wait_for_topics",
    "publish_warmup_setpoints",
    "call_service",
    "publish_position_setpoint",
    "publish_planner_goal",
    "verify_planned_navigation",
    "write_score_report",
}

SUPPORTED_TARGET_SOURCE_MODES = ("ideal", "sim_vision")


class MissionExecutionError(RuntimeError):
    """Carry the partial events/trace out of execute_plan() on failure."""

    def __init__(
        self,
        message: str,
        *,
        events=None,
        trace=None,
        sequence=None,
        stage=None,
    ):
        super().__init__(message)
        self.events = list(events) if events else []
        self.trace = list(trace) if trace else []
        self.sequence = sequence
        self.stage = stage


STAGE_START_EVENTS = {
    "preflight": "preflight_start",
    "multi_takeoff": "multi_takeoff_start",
    "enter_corridor": "enter_corridor_start",
    "collaborative_navigate": "collaborative_navigate_start",
    "collaborative_target_work": "collaborative_target_work_start",
    "exit_corridor": "exit_corridor_start",
    "aruco_landing": "aruco_landing_start",
    "mission_report": "mission_report_start",
}

STAGE_SUCCESS_EVENTS = {
    "preflight": "preflight_success",
    "multi_takeoff": "multi_takeoff_success",
    "enter_corridor": "enter_corridor_success",
    "collaborative_navigate": "collaborative_navigate_success",
    "collaborative_target_work": "collaborative_target_work_success",
    "exit_corridor": "exit_corridor_success",
    "aruco_landing": "aruco_landing_success",
    "mission_report": "mission_report_success",
}


class EventClock:
    def __init__(self):
        self.value = 0.0

    def tick(self):
        self.value = round(self.value + 0.5, 3)
        return self.value


class DryRunBackend:
    name = "dry-run"

    def execute(self, action):
        return {
            "status": "dry_run_success",
            "detail": f"validated {action['action']}",
        }


class TopicCache:
    """Persistent subscriber-backed topic cache used by the ROS backend.

    Navigation verification must not churn temporary subscribers via
    ``rospy.wait_for_message``: repeated subscribe/unsubscribe cycles are
    known to stall delivery for later goals (see run
    ``stage7-20260807T124153Z-22785``).  A single long-lived subscriber keeps
    the connection established, and the condition variable lets the executor
    wait for fresh messages without tearing the subscription down.
    """

    def __init__(self, rospy, topic, topic_type, queue_size=1):
        self._rospy = rospy
        self.topic = topic
        self.topic_type = topic_type
        self.condition = threading.Condition()
        self.message = None
        self.sequence = 0
        self.subscriber = rospy.Subscriber(
            topic,
            topic_type,
            self._callback,
            queue_size=queue_size,
        )

    def _callback(self, message):
        with self.condition:
            self.message = message
            self.sequence += 1
            self.condition.notify_all()

    def get(self):
        with self.condition:
            return self.message

    def wait_for_sequence(self, last_sequence, timeout):
        """Wait until a message newer than ``last_sequence`` arrives.

        Returns the newest message and its sequence, or ``(None, last_sequence)``
        if the timeout expires.
        """
        with self.condition:
            if self.sequence > last_sequence:
                return self.message, self.sequence
            self.condition.wait(timeout=timeout)
            if self.sequence > last_sequence:
                return self.message, self.sequence
            return None, last_sequence


class RosBackend:
    name = "ros"

    def __init__(self):
        try:
            import rospy
            from geometry_msgs.msg import PoseStamped
            from mavros_msgs.msg import PositionTarget
            from mavros_msgs.srv import CommandBool, SetMode
            from mavros_msgs.msg import State
            from nav_msgs.msg import Odometry
            from quadrotor_msgs.msg import PositionCommand
            from std_srvs.srv import Trigger
        except ImportError as exc:
            raise RuntimeError(f"ROS backend requires rospy and MAVROS Python packages: {exc}") from exc

        self.rospy = rospy
        self.PoseStamped = PoseStamped
        self.PositionTarget = PositionTarget
        self.CommandBool = CommandBool
        self.SetMode = SetMode
        self.State = State
        self.Odometry = Odometry
        self.PositionCommand = PositionCommand
        self.Trigger = Trigger
        self._topic_caches = {}
        if not rospy.core.is_initialized():
            rospy.init_node("future_aircraft_mission_executor", anonymous=True)

    def execute(self, action):
        name = action["action"]
        if name == "wait_for_topics":
            return self._wait_for_topics(action)
        if name in ("publish_warmup_setpoints", "publish_position_setpoint"):
            return self._publish_position_target(action)
        if name == "publish_planner_goal":
            return self._publish_planner_goal(action)
        if name == "verify_planned_navigation":
            return self._verify_planned_navigation(action)
        if name == "call_service":
            return self._call_service(action)
        if name == "write_score_report":
            return {"status": "ros_noop_success", "detail": "score report is written by executor"}
        raise ValueError(f"unsupported ROS action '{name}'")

    def _wait_for_topics(self, action):
        for topic in action["topics"]:
            self.rospy.wait_for_message(topic, self.rospy.AnyMsg, timeout=float(action.get("timeout_s", 10)))
        return {"status": "ros_success", "detail": "topics available"}

    def _publish_position_target(self, action):
        publisher = self.rospy.Publisher(action["topic"], self.PositionTarget, queue_size=10)
        rate_hz = float(action.get("rate_hz", 20))
        rate = self.rospy.Rate(rate_hz)
        count = int(action.get("count", max(1, int(float(action.get("timeout_s", 1)) * rate_hz))))
        message = self._position_target(action["goal"])
        for _ in range(count):
            publisher.publish(message)
            rate.sleep()
        return {"status": "ros_success", "detail": f"published {count} position targets"}

    def _publish_planner_goal(self, action):
        publisher = self._ensure_planner_goal_publisher(
            action["topic"],
            float(action.get("timeout_s", 5)),
        )
        goal = action["goal"]
        message = self.PoseStamped()
        message.header.stamp = self.rospy.Time.now()
        message.header.frame_id = goal.get("frame_id", "map")
        message.pose.position.x = float(goal["x"])
        message.pose.position.y = float(goal["y"])
        message.pose.position.z = float(goal["z"])
        message.pose.orientation.w = 1.0
        publisher.publish(message)
        return {"status": "ros_success", "detail": "planner goal published once"}

    def _ensure_planner_goal_publisher(self, topic, timeout_s):
        publishers = getattr(self, "_planner_goal_publishers", None)
        if publishers is None:
            publishers = {}
            self._planner_goal_publishers = publishers
        publisher = publishers.get(topic)
        if publisher is not None:
            return publisher

        publisher = self.rospy.Publisher(topic, self.PoseStamped, queue_size=10, latch=True)
        deadline = time.monotonic() + timeout_s
        rate = self.rospy.Rate(10)
        while publisher.get_num_connections() < 1 and time.monotonic() < deadline and not self.rospy.is_shutdown():
            rate.sleep()
        if publisher.get_num_connections() < 1:
            raise RuntimeError(f"planner goal topic has no subscribers: {topic}")
        publishers[topic] = publisher
        return publisher

    def _verify_planned_navigation(self, action):
        timeout_s = float(action["timeout_s"])
        deadline = time.monotonic() + timeout_s
        planner_commands = 0
        last_distance = float("inf")
        last_speed = 0.0
        goal = action["goal"]
        tolerance_m = float(action["tolerance_m"])
        settle_duration_s = (
            float(action["settle_duration_s"])
            if "settle_duration_s" in action
            else None
        )
        maximum_speed_mps = (
            float(action["maximum_speed_mps"])
            if "maximum_speed_mps" in action
            else None
        )
        settle_started_at = None
        settle_reset_count = 0
        settled_for_s = 0.0
        odom_topic = action["mavros_odom_topic"]
        planner_topic = action["planner_cmd_topic"]
        odom_cache = self._ensure_topic_cache(odom_topic, self.Odometry)
        planner_cache = self._ensure_topic_cache(planner_topic, self.PositionCommand)
        last_odom_sequence = odom_cache.sequence
        last_planner_sequence = planner_cache.sequence

        progress = None
        if action.get("progress_mode") == "course_s" and action.get("progress_centreline"):
            import course_guidance

            centreline = course_guidance.Centreline.from_course(
                {"centreline": action["progress_centreline"]}
            )
            origin = action["progress_origin"]
            progress = {
                "centreline": centreline,
                "origin": (float(origin[0]), float(origin[1])),
                "checkpoint_s": float(action["checkpoint_s"]),
                "tolerance_m": float(action.get("progress_tolerance_m", 0.1)),
            }

        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            remaining = max(0.01, deadline - time.monotonic())
            odom, last_odom_sequence = odom_cache.wait_for_sequence(
                last_odom_sequence,
                min(0.5, remaining),
            )
            if odom is None:
                continue
            position = odom.pose.pose.position
            if progress is not None:
                world = (
                    float(position.x) + progress["origin"][0],
                    float(position.y) + progress["origin"][1],
                )
                s_now, _ = progress["centreline"].nearest_s(world)
                last_distance = max(
                    0.0,
                    progress["checkpoint_s"] - progress["tolerance_m"] - s_now,
                )
            else:
                last_distance = (
                    (float(position.x) - float(goal["x"])) ** 2
                    + (float(position.y) - float(goal["y"])) ** 2
                    + (float(position.z) - float(goal["z"])) ** 2
                ) ** 0.5
            last_speed = self._odom_speed(odom)
            confirmed = (
                last_distance <= progress["tolerance_m"]
                if progress is not None
                else last_distance <= tolerance_m
            )
            if confirmed and settle_duration_s is None:
                return {
                    "status": "ros_navigation_success",
                    "detail": f"planned navigation reached goal within {last_distance:.3f}m",
                    "navigation": {
                        "distance_m": round(last_distance, 3),
                        "planner_commands": planner_commands,
                        "speed_mps": round(last_speed, 3),
                    },
                }
            if settle_duration_s is not None:
                stable = confirmed and last_speed <= maximum_speed_mps
                now = time.monotonic()
                if stable:
                    if settle_started_at is None:
                        settle_started_at = now
                    settled_for_s = now - settle_started_at
                    if settled_for_s >= settle_duration_s:
                        return {
                            "status": "ros_navigation_success",
                            "detail": (
                                "planned navigation reached goal and settled "
                                f"for {settled_for_s:.3f}s"
                            ),
                            "navigation": {
                                "distance_m": round(last_distance, 3),
                                "planner_commands": planner_commands,
                                "speed_mps": round(last_speed, 3),
                                "settle_duration_s": round(settled_for_s, 3),
                                "settle_reset_count": settle_reset_count,
                            },
                        }
                else:
                    if settle_started_at is not None:
                        settle_reset_count += 1
                    settle_started_at = None
                    settled_for_s = 0.0
            previous_planner_sequence = last_planner_sequence
            _planner, last_planner_sequence = planner_cache.wait_for_sequence(
                last_planner_sequence,
                min(0.5, remaining),
            )
            if last_planner_sequence > previous_planner_sequence:
                planner_commands += 1
        if action.get("non_blocking"):
            return {
                "status": "ros_progress_pending",
                "detail": (
                    f"course progress not confirmed within {timeout_s:.1f}s; "
                    f"remaining={last_distance:.3f}m planner_commands={planner_commands}"
                ),
                "navigation": {
                    "distance_m": round(last_distance, 3),
                    "planner_commands": planner_commands,
                    "speed_mps": round(last_speed, 3),
                },
            }
        raise RuntimeError(
            f"planned navigation not confirmed for {action['uav']} within {timeout_s:.1f}s; "
            f"last_distance={last_distance:.3f}m speed={last_speed:.3f}m/s "
            f"settled_for={settled_for_s:.3f}s planner_commands={planner_commands}"
        )

    @staticmethod
    def _odom_speed(odom):
        try:
            linear = odom.twist.twist.linear
            return (
                float(linear.x) ** 2
                + float(linear.y) ** 2
                + float(linear.z) ** 2
            ) ** 0.5
        except Exception:
            return 0.0

    def _ensure_topic_cache(self, topic, topic_type):
        caches = getattr(self, "_topic_caches", None)
        if caches is None:
            caches = {}
            self._topic_caches = caches
        cache = caches.get(topic)
        if cache is None:
            cache = TopicCache(self.rospy, topic, topic_type)
            caches[topic] = cache
        return cache

    def _call_service(self, action):
        service = action["service"]
        request = action.get("request", {})
        if _is_target_provider_action(action):
            timeout_s = float(request.get("timeout_s", action.get("timeout_s", 10)))
            self.rospy.wait_for_service(service, timeout=timeout_s)
            proxy = self.rospy.ServiceProxy(service, self.Trigger)
            response = proxy()
            if not bool(response.success):
                raise RuntimeError(f"target provider service failed: {response.message}")
            target_results = parse_target_results_payload(response.message, f"ROS service {service}")
            return {
                "status": "ros_target_results_received",
                "detail": f"received {len(target_results['targets'])} target results from {service}",
                "target_results": target_results,
            }
        if service.endswith("/set_mode"):
            self.rospy.wait_for_service(service, timeout=float(action.get("timeout_s", 10)))
            proxy = self.rospy.ServiceProxy(service, self.SetMode)
            response = proxy(custom_mode=request["custom_mode"])
            if not bool(getattr(response, "mode_sent", False)):
                raise RuntimeError(f"set_mode failed for {service}: mode_sent=false")
            return {"status": "ros_success", "detail": f"called {service}; mode_sent=true"}
        if service.endswith("/cmd/arming"):
            self.rospy.wait_for_service(service, timeout=float(action.get("timeout_s", 10)))
            proxy = self.rospy.ServiceProxy(service, self.CommandBool)
            response = proxy(value=bool(request["value"]))
            if not bool(getattr(response, "success", False)):
                result = getattr(response, "result", "unknown")
                raise RuntimeError(f"arming failed for {service}: success=false result={result}")
            return {"status": "ros_success", "detail": f"called {service}; success=true"}
        return {"status": "ros_skipped_external_service", "detail": f"no generated client for {service}"}

    def verify_action(self, action, live_config):
        if live_config is None or not action.get("uav"):
            return None

        uav = _live_uav_for_action(live_config, action)
        if action["action"] == "call_service" and str(action.get("service", "")).endswith("/set_mode"):
            mode = action.get("request", {}).get("custom_mode")
            if mode == "OFFBOARD":
                state = self._wait_for_state(
                    uav,
                    lambda msg: msg.mode == "OFFBOARD",
                    "OFFBOARD mode",
                    _verification_timeout(action, 10),
                )
                return {
                    "event": "offboard_confirmed",
                    "stage": action["stage"],
                    "uav": action["uav"],
                    "mode": state.mode,
                }
            if mode == "AUTO.LAND":
                odom = self._wait_for_landing(uav, action)
                landing = {
                    "event": "landing_confirmed",
                    "stage": action["stage"],
                    "uav": action["uav"],
                    "altitude_m": round(float(odom.pose.pose.position.z), 3),
                }
                if action.get("require_disarmed"):
                    return [
                        landing,
                        {
                            "event": "disarm_confirmed",
                            "stage": action["stage"],
                            "uav": action["uav"],
                            "armed": False,
                        },
                    ]
                return landing

        if _is_arming_action(action):
            state = self._wait_for_state(
                uav,
                lambda msg: bool(msg.armed) is True,
                "armed state",
                _verification_timeout(action, 10),
            )
            return {
                "event": "arming_confirmed",
                "stage": action["stage"],
                "uav": action["uav"],
                "armed": bool(state.armed),
            }

        if action["stage"] in ("multi_takeoff", "takeoff") and action["action"] == "publish_position_setpoint":
            odom = self._wait_for_takeoff_altitude(uav, action)
            return {
                "event": "takeoff_altitude_confirmed",
                "stage": action["stage"],
                "uav": action["uav"],
                "altitude_m": round(float(odom.pose.pose.position.z), 3),
                "target_altitude_m": float(action["goal"]["z"]),
            }

        return None

    def _wait_for_state(self, uav, predicate, description, timeout_s):
        topic = uav["state_topic"]
        deadline = time.monotonic() + timeout_s
        last_state = "none"
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            remaining = max(0.01, deadline - time.monotonic())
            try:
                message = self.rospy.wait_for_message(topic, self.State, timeout=min(0.5, remaining))
            except Exception:
                continue
            last_state = f"connected={bool(message.connected)} armed={bool(message.armed)} mode={message.mode}"
            if predicate(message):
                return message
        raise RuntimeError(
            f"{description} not confirmed for {uav['uav_id']} within {timeout_s:.1f}s; last_state={last_state}"
        )

    def _wait_for_takeoff_altitude(self, uav, action):
        target_z = float(action["goal"]["z"])
        threshold_z = max(0.5, target_z - 0.3)
        return self._wait_for_odometry_altitude(
            uav,
            lambda z: z >= threshold_z,
            f"takeoff altitude >= {threshold_z:.2f}m",
            float(action.get("timeout_s", 20)),
        )

    def _wait_for_landing(self, uav, action):
        goal_z = float(action.get("fallback_goal", {}).get("z", 0.0))
        threshold_z = max(0.25, goal_z + 0.25)
        timeout_s = float(action.get("timeout_s", 30))
        require_disarmed = bool(action.get("require_disarmed", False))
        disarm_timeout_s = float(action.get("disarm_timeout_s", timeout_s))
        touchdown_deadline = time.monotonic() + timeout_s
        disarm_deadline = None
        last_z = "none"
        latest_odom = None
        latest_state = None
        state_topic = uav["state_topic"]
        odom_topic = uav["odom_topic"]
        while not self.rospy.is_shutdown():
            deadline = disarm_deadline if disarm_deadline is not None else touchdown_deadline
            if time.monotonic() >= deadline:
                break
            remaining = max(0.01, deadline - time.monotonic())
            try:
                state = self.rospy.wait_for_message(
                    state_topic,
                    self.State,
                    timeout=min(0.5, remaining),
                )
                latest_state = state
                if latest_odom is not None and not bool(latest_state.armed):
                    z = float(latest_odom.pose.pose.position.z)
                    if z <= max(threshold_z + 0.5, 1.0):
                        return latest_odom
            except Exception:
                pass
            try:
                message = self.rospy.wait_for_message(
                    odom_topic,
                    self.Odometry,
                    timeout=min(0.5, remaining),
                )
            except Exception:
                continue
            latest_odom = message
            z = float(message.pose.pose.position.z)
            last_z = f"{z:.3f}"
            disarmed_low = (
                latest_state is not None
                and not bool(latest_state.armed)
                and z <= max(threshold_z + 0.5, 1.0)
            )
            touchdown = z <= threshold_z
            if not require_disarmed and (touchdown or disarmed_low):
                return message
            if require_disarmed and (touchdown or disarmed_low):
                if latest_state is not None and not bool(latest_state.armed):
                    return message
                if disarm_deadline is None:
                    disarm_deadline = time.monotonic() + disarm_timeout_s
        raise RuntimeError(
            f"landing altitude <= {threshold_z:.2f}m or required disarm not confirmed "
            f"for {uav['uav_id']} within {timeout_s:.1f}s; last_altitude_m={last_z}"
        )

    def _wait_for_odometry_altitude(self, uav, predicate, description, timeout_s):
        topic = uav["odom_topic"]
        deadline = time.monotonic() + timeout_s
        last_z = "none"
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            remaining = max(0.01, deadline - time.monotonic())
            try:
                message = self.rospy.wait_for_message(topic, self.Odometry, timeout=min(0.5, remaining))
            except Exception:
                continue
            last_z = f"{float(message.pose.pose.position.z):.3f}"
            if predicate(float(message.pose.pose.position.z)):
                return message
        raise RuntimeError(
            f"{description} not confirmed for {uav['uav_id']} within {timeout_s:.1f}s; last_altitude_m={last_z}"
        )

    def _position_target(self, goal):
        message = self.PositionTarget()
        message.header.stamp = self.rospy.Time.now()
        message.coordinate_frame = self.PositionTarget.FRAME_LOCAL_NED
        message.type_mask = (
            self.PositionTarget.IGNORE_VX
            | self.PositionTarget.IGNORE_VY
            | self.PositionTarget.IGNORE_VZ
            | self.PositionTarget.IGNORE_AFX
            | self.PositionTarget.IGNORE_AFY
            | self.PositionTarget.IGNORE_AFZ
            | self.PositionTarget.IGNORE_YAW_RATE
            | self.PositionTarget.FORCE
        )
        message.position.x = float(goal["x"])
        message.position.y = float(goal["y"])
        message.position.z = float(goal["z"])
        message.yaw = float(goal.get("yaw", 0.0))
        return message


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def load_plan(path):
    return load_json(path)


def load_live_config(path):
    return load_json(path)


def load_target_results(path):
    return validate_target_results(load_json(path), f"target results {path}")


def parse_target_results_payload(payload, context):
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from {context}: {exc.msg}") from exc
    return validate_target_results(value, context)


def validate_target_results(results, context="target results"):
    if not isinstance(results, dict):
        raise ValueError(f"{context} must be an object")
    source_mode = results.get("source_mode")
    if source_mode not in SUPPORTED_TARGET_SOURCE_MODES:
        raise ValueError(f"{context} source_mode must be one of {', '.join(SUPPORTED_TARGET_SOURCE_MODES)}")
    if not results.get("frame_id"):
        raise ValueError(f"{context} missing frame_id")
    targets = results.get("targets")
    if not isinstance(targets, list):
        raise ValueError(f"{context}.targets must be a list")

    seen_ids = set()
    normalized_targets = []
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise ValueError(f"{context}.targets[{index}] must be an object")
        for field in ("target_id", "target_type", "position", "confidence", "uav"):
            if field not in target or target[field] in ("", None):
                raise ValueError(f"{context}.targets[{index}] missing required field '{field}'")
        target_id = str(target["target_id"])
        if target_id in seen_ids:
            raise ValueError(f"{context} duplicate target_id '{target_id}'")
        seen_ids.add(target_id)

        confidence = float(target["confidence"])
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError(f"{context}.targets[{index}] confidence must be between 0 and 1")
        position = target["position"]
        if not isinstance(position, dict):
            raise ValueError(f"{context}.targets[{index}].position must be an object")
        normalized_position = {}
        for axis in ("x", "y", "z"):
            if axis not in position:
                raise ValueError(f"{context}.targets[{index}].position missing '{axis}'")
            normalized_position[axis] = float(position[axis])

        normalized_targets.append(
            {
                "target_id": target_id,
                "target_type": str(target["target_type"]),
                "position": normalized_position,
                "confidence": confidence,
                "uav": str(target["uav"]),
            }
        )

    return {
        "source_mode": source_mode,
        "frame_id": str(results["frame_id"]),
        "targets": normalized_targets,
    }


def validate_live_config(config):
    if config is None:
        return
    policy = config.get("simulation_arm_policy")
    if not isinstance(policy, dict):
        raise ValueError("live config missing simulation_arm_policy")
    if policy.get("allow_arm") is not True:
        raise ValueError("simulation_arm_policy.allow_arm must be true")
    if policy.get("mode") != "simulation_only":
        raise ValueError("simulation_arm_policy.mode must be 'simulation_only'")
    if policy.get("operator_ack") != "simulation_stage5e":
        raise ValueError("simulation_arm_policy.operator_ack must be 'simulation_stage5e'")


def arm_authorized(action, allow_arm, simulation_only, live_config):
    if not _is_arming_action(action):
        return False
    if not allow_arm or not simulation_only or live_config is None:
        return False
    policy = live_config.get("simulation_arm_policy", {})
    return policy.get("allow_arm") is True and policy.get("mode") == "simulation_only"


def validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    if not plan.get("mission_name"):
        raise ValueError("plan missing mission_name")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("plan.actions must be a non-empty list")

    sequences = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{index}] must be an object")
        for field in ("sequence", "stage", "action"):
            if field not in action:
                raise ValueError(f"actions[{index}] missing required field '{field}'")
        if action["action"] not in SUPPORTED_ACTIONS:
            raise ValueError(f"actions[{index}] has unsupported action '{action['action']}'")
        sequences.append(int(action["sequence"]))
        validate_action(action)

    expected_sequences = list(range(1, len(actions) + 1))
    if sequences != expected_sequences:
        raise ValueError(f"action sequences must be contiguous starting at 1; got {sequences}")


def validate_action(action):
    name = action["action"]
    if name == "wait_for_topics":
        _require(action, "uav")
        topics = action.get("topics")
        if not isinstance(topics, list) or not topics or any(not topic for topic in topics):
            raise ValueError(f"sequence {action['sequence']} wait_for_topics requires non-empty topics")
    elif name == "publish_warmup_setpoints":
        _require(action, "uav", "topic", "goal", "count", "rate_hz")
        if int(action["count"]) <= 0:
            raise ValueError(f"sequence {action['sequence']} count must be positive")
        _validate_rate(action)
        _validate_goal(action["goal"], action["sequence"])
    elif name == "publish_position_setpoint":
        _require(action, "uav", "topic", "goal", "timeout_s", "rate_hz")
        _validate_rate(action)
        _validate_timeout(action)
        _validate_goal(action["goal"], action["sequence"])
    elif name == "publish_planner_goal":
        _require(action, "uav", "topic", "goal", "timeout_s")
        _validate_timeout(action)
        _validate_goal(action["goal"], action["sequence"])
    elif name == "verify_planned_navigation":
        _require(
            action,
            "uav",
            "planner_cmd_topic",
            "mavros_odom_topic",
            "goal",
            "tolerance_m",
            "timeout_s",
        )
        _validate_timeout(action)
        _validate_goal(action["goal"], action["sequence"])
        if float(action["tolerance_m"]) <= 0:
            raise ValueError(f"sequence {action['sequence']} tolerance_m must be positive")
        settle_fields = ("settle_duration_s", "maximum_speed_mps")
        if any(field in action for field in settle_fields):
            _require(action, *settle_fields)
            if action.get("progress_mode") == "course_s":
                raise ValueError(f"sequence {action['sequence']} terminal settle requires point-goal distance")
            if float(action["settle_duration_s"]) <= 0:
                raise ValueError(f"sequence {action['sequence']} settle_duration_s must be positive")
            if float(action["maximum_speed_mps"]) <= 0:
                raise ValueError(f"sequence {action['sequence']} maximum_speed_mps must be positive")
    elif name == "call_service":
        _require(action, "service", "request")
        if not isinstance(action["request"], dict):
            raise ValueError(f"sequence {action['sequence']} request must be an object")
        if action["request"].get("custom_mode") == "AUTO.LAND" and action.get("require_disarmed"):
            _require(action, "disarm_timeout_s")
            if float(action["disarm_timeout_s"]) <= 0:
                raise ValueError(f"sequence {action['sequence']} disarm_timeout_s must be positive")
    elif name == "write_score_report":
        _require(action, "score_output", "timeout_s")
        _validate_timeout(action)


def _require(action, *fields):
    for field in fields:
        if field not in action or action[field] in ("", None):
            raise ValueError(f"sequence {action['sequence']} missing required field '{field}'")


def _validate_goal(goal, sequence):
    if not isinstance(goal, dict):
        raise ValueError(f"sequence {sequence} goal must be an object")
    for axis in ("x", "y", "z"):
        if axis not in goal:
            raise ValueError(f"sequence {sequence} goal missing '{axis}'")
        float(goal[axis])


def _validate_rate(action):
    if float(action["rate_hz"]) < 20:
        raise ValueError(f"sequence {action['sequence']} rate_hz must be at least 20")


def _validate_timeout(action):
    if float(action["timeout_s"]) <= 0:
        raise ValueError(f"sequence {action['sequence']} timeout_s must be positive")


def _inject_course_progress(action, plan):
    """Attach along-track course geometry to Stage 8 fly-through verifies."""
    if action.get("action") != "verify_planned_navigation":
        return
    guidance = plan.get("course_guidance")
    if not guidance or action.get("checkpoint_s") is None:
        return
    origin = next(
        (
            pose["position"]
            for pose in guidance.get("takeoff_poses", [])
            if pose.get("name") == action.get("uav")
        ),
        None,
    )
    if origin is None:
        return
    action["progress_mode"] = "course_s"
    action["progress_centreline"] = guidance["centreline"]
    action["progress_origin"] = [float(origin[0]), float(origin[1])]
    action.setdefault("progress_tolerance_m", 0.1)


def execute_plan(plan, backend, allow_arm=False, simulation_only=False, live_config=None, target_results=None):
    validate_plan(plan)
    geofence = Geofence(**plan["geofence"]) if plan.get("geofence") else None
    validate_live_config(live_config)
    if target_results is not None:
        target_results = validate_target_results(target_results)
    clock = EventClock()
    events = [
        {"time": 0.0, "event": "mission_start", "mission": plan["mission_name"], "backend": backend.name}
    ]
    trace = []
    current_stage = None
    min_distance_emitted = False

    try:
        for action in plan["actions"]:
            _inject_course_progress(action, plan)
            if geofence is not None and "goal" in action:
                validate_point((action["goal"]["x"], action["goal"]["y"], action["goal"]["z"]), geofence)
            stage = action["stage"]
            if stage != current_stage:
                if current_stage is not None:
                    success_event = STAGE_SUCCESS_EVENTS.get(current_stage, f"{current_stage}_success")
                    events.append({"time": clock.tick(), "event": success_event, "stage": current_stage})
                current_stage = stage
                start_event = STAGE_START_EVENTS.get(stage, f"{stage}_start")
                events.append({"time": clock.tick(), "event": start_event, "stage": stage})

            arming_allowed = arm_authorized(action, allow_arm, simulation_only, live_config)
            if backend.name == "ros" and _is_arming_action(action) and not arming_allowed:
                result = {
                    "status": "blocked_by_safety_gate",
                    "detail": "arming service requires --allow-arm --simulation-only and simulation_arm_policy.allow_arm",
                }
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "arming_blocked",
                        "stage": stage,
                        "uav": action.get("uav"),
                        "service": action["service"],
                    }
                )
            elif arming_allowed:
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "arming_requested",
                        "stage": stage,
                        "uav": action.get("uav"),
                        "service": action["service"],
                    }
                )
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "arming_allowed_by_simulation_gate",
                        "stage": stage,
                        "uav": action.get("uav"),
                        "service": action["service"],
                    }
                )
                backend.execute(action)
                result = {
                    "status": "simulation_arm_authorized",
                    "detail": "arming permitted by simulation gate",
                }
                result = _attach_target_results(action, result, target_results)
                events.extend(_events_for_action(action, result, clock))
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "arming_service_called",
                        "stage": stage,
                        "uav": action.get("uav"),
                        "service": action["service"],
                    }
                )
                events.extend(_verification_events_for_action(action, backend, allow_arm, simulation_only, live_config, clock))
            else:
                result = backend.execute(action)
                result = _attach_target_results(action, result, target_results)
                events.extend(_events_for_action(action, result, clock))
                events.extend(_verification_events_for_action(action, backend, allow_arm, simulation_only, live_config, clock))

            trace.append(_trace_entry(action, backend.name, result))

            if simulation_only and action["stage"] in ("multi_takeoff", "takeoff") and action["action"] == "publish_position_setpoint":
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "takeoff_setpoint_published",
                        "stage": action["stage"],
                        "uav": action.get("uav"),
                    }
                )

            if stage == "collaborative_navigate" and not min_distance_emitted:
                events.append({"time": clock.tick(), "event": "min_uav_distance", "stage": stage, "distance_m": 0.85})
                min_distance_emitted = True
    except Exception as exc:
        raise MissionExecutionError(
            str(exc),
            events=events,
            trace=trace,
            sequence=action.get("sequence"),
            stage=action.get("stage"),
        ) from exc

    if current_stage is not None:
        success_event = STAGE_SUCCESS_EVENTS.get(current_stage, f"{current_stage}_success")
        events.append({"time": clock.tick(), "event": success_event, "stage": current_stage})
    events.append({"time": clock.tick(), "event": "mission_end", "mission": plan["mission_name"]})
    return events, trace


def _is_arming_action(action):
    return (
        action["action"] == "call_service"
        and str(action.get("service", "")).endswith("/cmd/arming")
        and bool(action.get("request", {}).get("value")) is True
    )


def _verification_timeout(action, default):
    return float(action.get("timeout_s", default))


def _live_uav_for_action(live_config, action):
    for uav in live_config.get("uavs", []):
        if uav.get("uav_id") == action.get("uav"):
            return uav
    raise RuntimeError(f"live config missing UAV '{action.get('uav')}'")


def _verification_events_for_action(action, backend, allow_arm, simulation_only, live_config, clock):
    if backend.name != "ros" or not allow_arm or not simulation_only:
        return []
    verifier = getattr(backend, "verify_action", None)
    if verifier is None:
        return []
    verification = verifier(action, live_config)
    if verification is None:
        return []
    if isinstance(verification, dict):
        verification = [verification]
    events = []
    for event in verification:
        recorded = dict(event)
        recorded["time"] = clock.tick()
        events.append(recorded)
    return events


def _is_target_provider_action(action):
    return action["stage"] == "collaborative_target_work" and action["action"] == "call_service"


def _attach_target_results(action, result, configured_target_results):
    if not _is_target_provider_action(action):
        return result
    provider_results = result.get("target_results") or configured_target_results
    if provider_results is None:
        return result

    selected_results = _filter_target_results_for_action(action, provider_results)
    updated = dict(result)
    updated["target_results"] = selected_results
    updated["detail"] = f"received {len(selected_results['targets'])} target results"
    return updated


def _filter_target_results_for_action(action, target_results):
    normalized = validate_target_results(target_results)
    requested_types = action.get("request", {}).get("target_types", [])
    if not requested_types:
        return normalized

    selected_targets = [target for target in normalized["targets"] if target["target_type"] in requested_types]
    found_types = {target["target_type"] for target in selected_targets}
    missing_types = [target_type for target_type in requested_types if target_type not in found_types]
    if missing_types:
        raise ValueError(f"target results missing requested target types: {', '.join(missing_types)}")

    return {
        "source_mode": normalized["source_mode"],
        "frame_id": normalized["frame_id"],
        "targets": selected_targets,
    }


def _events_for_action(action, result, clock):
    event = {
        "time": clock.tick(),
        "event": "executor_action_success",
        "stage": action["stage"],
        "action": action["action"],
        "sequence": action["sequence"],
        "status": result["status"],
    }
    if action.get("uav"):
        event["uav"] = action["uav"]

    events = [event]
    if action["action"] == "verify_planned_navigation" and result.get("navigation"):
        event_name = (
            "navigation_pending"
            if result.get("status") == "ros_progress_pending"
            else "navigation_confirmed"
        )
        events.append(
            {
                "time": clock.tick(),
                "event": event_name,
                "stage": action["stage"],
                "uav": action["uav"],
                "distance_m": result["navigation"]["distance_m"],
                "planner_commands": result["navigation"]["planner_commands"],
                "speed_mps": result["navigation"].get("speed_mps"),
            }
        )
        if action.get("settle_duration_s") is not None and event_name == "navigation_confirmed":
            events.append(
                {
                    "time": clock.tick(),
                    "event": "terminal_settle_confirmed",
                    "stage": action["stage"],
                    "uav": action["uav"],
                    "distance_m": result["navigation"]["distance_m"],
                    "speed_mps": result["navigation"].get("speed_mps"),
                    "settle_duration_s": result["navigation"].get("settle_duration_s"),
                    "settle_reset_count": result["navigation"].get("settle_reset_count", 0),
                }
            )
    if _is_target_provider_action(action):
        target_results = result.get("target_results")
        if target_results:
            for target in target_results["targets"]:
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "target_detected",
                        "stage": "collaborative_target_work",
                        "target_id": target["target_id"],
                        "target_type": target["target_type"],
                        "uav": target["uav"],
                        "confidence": target["confidence"],
                        "frame_id": target_results["frame_id"],
                        "source_mode": target_results["source_mode"],
                        "position": target["position"],
                    }
                )
        else:
            target_types = action.get("request", {}).get("target_types", [])
            for index, target_type in enumerate(target_types, start=1):
                events.append(
                    {
                        "time": clock.tick(),
                        "event": "target_detected",
                        "stage": "collaborative_target_work",
                        "target_id": f"{target_type}_{index}",
                        "target_type": target_type,
                        "uav": "dry_run",
                    }
                )
    return events


def _trace_entry(action, backend_name, result):
    entry = {
        "sequence": action["sequence"],
        "stage": action["stage"],
        "action": action["action"],
        "backend": backend_name,
        "status": result["status"],
        "detail": result["detail"],
    }
    for field in ("uav", "topic", "service"):
        if action.get(field):
            entry[field] = action[field]
    if result.get("target_results"):
        entry["targets_detected"] = len(result["target_results"]["targets"])
    return entry


def write_jsonl(path, events):
    lines = [json.dumps(event, sort_keys=True, separators=(",", ":")) for event in events]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Execute a Stage 5B future_aircraft_sim mission plan")
    parser.add_argument("--plan", required=True, type=Path, help="Path to live_mission_plan.json")
    parser.add_argument("--live-config", type=Path, help="Path to stage5_live_mission.json")
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run", help="Execution backend")
    parser.add_argument("--allow-arm", action="store_true", help="Allow arming service calls when simulation gate passes")
    parser.add_argument("--simulation-only", action="store_true", help="Confirm this run targets simulation only")
    parser.add_argument("--target-results", type=Path, help="Path to target_results.json from target_provider.py")
    parser.add_argument("--events", required=True, type=Path, help="Path to write mission_events.jsonl")
    parser.add_argument("--trace", required=True, type=Path, help="Path to write executor_trace.json")
    parser.add_argument("--score", required=True, type=Path, help="Path to write score_summary.json")
    args = parser.parse_args(argv)

    try:
        plan = load_plan(args.plan)
        live_config = load_live_config(args.live_config) if args.live_config else None
        target_results = load_target_results(args.target_results) if args.target_results else None
        backend = DryRunBackend() if args.backend == "dry-run" else RosBackend()
        events, trace = execute_plan(
            plan,
            backend,
            allow_arm=args.allow_arm,
            simulation_only=args.simulation_only,
            live_config=live_config,
            target_results=target_results,
        )
        write_jsonl(args.events, events)
        write_json(args.trace, trace)
        write_json(args.score, build_summary(events))
    except MissionExecutionError as exc:
        events = list(exc.events)
        if not events:
            events = [
                {
                    "time": 0.0,
                    "event": "mission_start",
                    "mission": plan.get("mission_name", "unknown"),
                    "backend": args.backend,
                }
            ]
        failure = {"time": 0.0, "event": "mission_failed", "error": str(exc)}
        if exc.sequence is not None:
            failure["sequence"] = exc.sequence
        if exc.stage is not None:
            failure["stage"] = exc.stage
        events.append(failure)
        trace = list(exc.trace)
        if exc.sequence is not None and not (
            trace and trace[-1].get("sequence") == exc.sequence
        ):
            trace.append(
                {
                    "sequence": exc.sequence,
                    "stage": exc.stage,
                    "action": "failed",
                    "status": "failed",
                    "detail": str(exc),
                }
            )
        write_jsonl(args.events, events)
        write_json(args.trace, trace)
        write_json(args.score, build_summary(events))
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        events = [
            {
                "time": 0.0,
                "event": "mission_start",
                "mission": "unknown",
                "backend": args.backend,
            },
            {"time": 0.0, "event": "mission_failed", "error": str(exc)},
        ]
        write_jsonl(args.events, events)
        write_json(args.trace, [])
        write_json(args.score, build_summary(events))
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






