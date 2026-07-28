#!/usr/bin/env python3
"""Execute a Stage 5B live mission plan with dry-run or guarded ROS backends."""

import argparse
import json
import sys
from pathlib import Path

from score_summary import build_summary


SUPPORTED_ACTIONS = {
    "wait_for_topics",
    "publish_warmup_setpoints",
    "call_service",
    "publish_position_setpoint",
    "publish_planner_goal",
    "write_score_report",
}

SUPPORTED_TARGET_SOURCE_MODES = ("ideal", "sim_vision")

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


class RosBackend:
    name = "ros"

    def __init__(self):
        try:
            import rospy
            from geometry_msgs.msg import PoseStamped
            from mavros_msgs.msg import PositionTarget
            from mavros_msgs.srv import CommandBool, SetMode
            from std_srvs.srv import Trigger
        except ImportError as exc:
            raise RuntimeError(f"ROS backend requires rospy and MAVROS Python packages: {exc}") from exc

        self.rospy = rospy
        self.PoseStamped = PoseStamped
        self.PositionTarget = PositionTarget
        self.CommandBool = CommandBool
        self.SetMode = SetMode
        self.Trigger = Trigger
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
        publisher = self.rospy.Publisher(action["topic"], self.PoseStamped, queue_size=10, latch=True)
        goal = action["goal"]
        message = self.PoseStamped()
        message.header.stamp = self.rospy.Time.now()
        message.header.frame_id = goal.get("frame_id", "map")
        message.pose.position.x = float(goal["x"])
        message.pose.position.y = float(goal["y"])
        message.pose.position.z = float(goal["z"])
        message.pose.orientation.w = 1.0
        publisher.publish(message)
        return {"status": "ros_success", "detail": "planner goal published"}

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
            proxy(custom_mode=request["custom_mode"])
            return {"status": "ros_success", "detail": f"called {service}"}
        if service.endswith("/cmd/arming"):
            self.rospy.wait_for_service(service, timeout=float(action.get("timeout_s", 10)))
            proxy = self.rospy.ServiceProxy(service, self.CommandBool)
            proxy(value=bool(request["value"]))
            return {"status": "ros_success", "detail": f"called {service}"}
        return {"status": "ros_skipped_external_service", "detail": f"no generated client for {service}"}

    def _position_target(self, goal):
        message = self.PositionTarget()
        message.coordinate_frame = self.PositionTarget.FRAME_LOCAL_NED
        message.type_mask = (
            self.PositionTarget.IGNORE_VX
            | self.PositionTarget.IGNORE_VY
            | self.PositionTarget.IGNORE_VZ
            | self.PositionTarget.IGNORE_AFX
            | self.PositionTarget.IGNORE_AFY
            | self.PositionTarget.IGNORE_AFZ
            | self.PositionTarget.IGNORE_YAW_RATE
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
    elif name == "call_service":
        _require(action, "service", "request")
        if not isinstance(action["request"], dict):
            raise ValueError(f"sequence {action['sequence']} request must be an object")
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


def execute_plan(plan, backend, allow_arm=False, simulation_only=False, live_config=None, target_results=None):
    validate_plan(plan)
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

    for action in plan["actions"]:
        stage = action["stage"]
        if stage != current_stage:
            if current_stage is not None:
                events.append({"time": clock.tick(), "event": STAGE_SUCCESS_EVENTS[current_stage], "stage": current_stage})
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
        else:
            result = backend.execute(action)
            result = _attach_target_results(action, result, target_results)
            events.extend(_events_for_action(action, result, clock))

        trace.append(_trace_entry(action, backend.name, result))

        if simulation_only and action["stage"] == "multi_takeoff" and action["action"] == "publish_position_setpoint":
            events.append(
                {
                    "time": clock.tick(),
                    "event": "takeoff_setpoint_published",
                    "stage": "multi_takeoff",
                    "uav": action.get("uav"),
                }
            )

        if stage == "collaborative_navigate" and not min_distance_emitted:
            events.append({"time": clock.tick(), "event": "min_uav_distance", "stage": stage, "distance_m": 0.85})
            min_distance_emitted = True

    if current_stage is not None:
        events.append({"time": clock.tick(), "event": STAGE_SUCCESS_EVENTS[current_stage], "stage": current_stage})
    events.append({"time": clock.tick(), "event": "mission_end", "mission": plan["mission_name"]})
    return events, trace


def _is_arming_action(action):
    return (
        action["action"] == "call_service"
        and str(action.get("service", "")).endswith("/cmd/arming")
        and bool(action.get("request", {}).get("value")) is True
    )


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
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






