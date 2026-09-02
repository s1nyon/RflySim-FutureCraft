#!/usr/bin/env python3
"""Generate the Stage 6C live dual-MAVROS smoke runbook without launching anything."""

import argparse
import json
import os
import re
import sys
from pathlib import Path


REQUIRED_ENV_KEYS = (
    "RFLYSIM_ROOT",
    "PSP_PATH",
    "PSP_PATH_LINUX",
    "RFLYSIM_WSL_DISTRO",
    "RFLYSIM_VCXSRV_DIR",
    "REF_28COM_UAV_DIR",
    "REF_28COM_UAV_WSL_DIR",
    "FUTURE_AIRCRAFT_WS",
    "FUTURE_AIRCRAFT_SIM_WSL_DIR",
    "ROS_DISTRO",
    "PYTHON_EXE",
)

WINDOWS_PATH_KEYS = (
    "RFLYSIM_ROOT",
    "PSP_PATH",
    "RFLYSIM_VCXSRV_DIR",
    "REF_28COM_UAV_DIR",
    "FUTURE_AIRCRAFT_WS",
    "PYTHON_EXE",
)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def parse_env_template(path):
    values = {}
    set_line = re.compile(r"^\s*set\s+([^=]+)=(.*)$", re.IGNORECASE)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = set_line.match(raw_line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        values[key] = value

    resolved = {}
    for key, value in values.items():
        resolved[key] = expand_percent_vars(value, {**values, **resolved})
    return resolved


def expand_percent_vars(value, variables):
    pattern = re.compile(r"%([^%]+)%")

    def replace(match):
        return variables.get(match.group(1), match.group(0))

    previous = None
    current = value
    for _ in range(8):
        if current == previous:
            break
        previous = current
        current = pattern.sub(replace, current)
    return current


def windows_string_for_env(path):
    value = str(path)
    match = re.match(r"^/mnt/([A-Za-z])/(.*)$", value)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"
    return value


def complete_env(env, project_root):
    env.setdefault("FUTURE_AIRCRAFT_SIM_DIR", windows_string_for_env(project_root))
    for key, value in list(env.items()):
        env[key] = expand_percent_vars(value, env)
    return env


def validate_env(env):
    missing = [key for key in REQUIRED_ENV_KEYS if not env.get(key)]
    if missing:
        raise ValueError(f"env template missing required keys: {', '.join(missing)}")
    if env["RFLYSIM_WSL_DISTRO"] != "RflySim-20.04":
        raise ValueError("RFLYSIM_WSL_DISTRO must be RflySim-20.04")
    if env["ROS_DISTRO"] != "noetic":
        raise ValueError("ROS_DISTRO must be noetic")


def validate_live_config(config):
    if config.get("mission_mode") != "live_ros_boundary":
        raise ValueError("mission_mode must be live_ros_boundary")
    if float(config.get("setpoint_rate_hz", 0)) < 20:
        raise ValueError("setpoint_rate_hz must be at least 20")
    uavs = config.get("uavs")
    if not isinstance(uavs, list) or [uav.get("uav_id") for uav in uavs] != ["uav1", "uav2"]:
        raise ValueError("live config must define uav1 and uav2 in order")


def validate_plan(plan):
    if not isinstance(plan.get("actions"), list) or not plan["actions"]:
        raise ValueError("live mission plan must contain actions")
    arming_actions = [
        action for action in plan["actions"]
        if action.get("action") == "call_service"
        and str(action.get("service", "")).endswith("/cmd/arming")
        and bool(action.get("request", {}).get("value")) is True
    ]
    if len(arming_actions) != 2:
        raise ValueError("live mission plan must contain exactly two true arming actions")


def path_exists_for_host(value):
    path = translate_path_for_host(value)
    return path.exists()


def translate_path_for_host(value):
    if os.name == "nt":
        return Path(value)
    match = re.match(r"^([A-Za-z]):\\(.*)$", value)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest}")
    return Path(value)


def rel(path, project_root):
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("/", "\\")
    except ValueError:
        return path.name


def build_environment(env):
    return {
        "windows_paths": [
            {"key": key, "value": env[key], "exists": path_exists_for_host(env[key])}
            for key in WINDOWS_PATH_KEYS
        ],
        "wsl": {
            "distro": env["RFLYSIM_WSL_DISTRO"],
            "psp_path": env["PSP_PATH_LINUX"],
            "ros_setup": "/opt/ros/noetic/setup.bash",
            "ref_28com_uav_dir": env["REF_28COM_UAV_WSL_DIR"],
            "future_aircraft_sim_dir": env["FUTURE_AIRCRAFT_SIM_WSL_DIR"],
        },
    }


def build_sequence(project_root, env, live_config, plan_path):
    python_exe = env["PYTHON_EXE"]
    live_config_rel = "config\\stage5_live_mission.json"
    plan_rel = "logs\\stage6c_live\\live_mission_plan.json"
    smoke_report = "logs\\stage6c_live\\mavros_smoke_report.json"
    events = "logs\\stage6c_live\\mission_events_no_arm.jsonl"
    trace = "logs\\stage6c_live\\executor_trace_no_arm.json"
    score = "logs\\stage6c_live\\score_summary_no_arm.json"

    return [
        {
            "step": 1,
            "id": "start_dual_uav_stack",
            "command": "scripts\\start_two_uav.bat",
            "launches_gui": True,
            "read_only": False,
            "arms_vehicle": False,
            "requires_operator_confirmation": True,
            "expected_result": "RflySim, PX4 SITL, WSL, and /uav1 + /uav2 MAVROS instances are running",
        },
        {
            "step": 2,
            "id": "mavros_read_only_smoke",
            "command": f"{python_exe} future_aircraft_ws\\src\\multi_uav_mission\\scripts\\mavros_smoke_check.py --live-config {live_config_rel} --backend ros --timeout-s 10 --report {smoke_report}",
            "launches_gui": False,
            "read_only": True,
            "arms_vehicle": False,
            "requires_operator_confirmation": False,
            "expected_result": "state and odom topics plus set_mode and arming services are available for both UAVs",
        },
        {
            "step": 3,
            "id": "mission_executor_no_arm_smoke",
            "command": f"{python_exe} future_aircraft_ws\\src\\multi_uav_mission\\scripts\\mission_executor.py --plan {plan_rel} --live-config {live_config_rel} --backend ros --events {events} --trace {trace} --score {score}",
            "launches_gui": False,
            "read_only": False,
            "arms_vehicle": False,
            "requires_operator_confirmation": False,
            "expected_result": "arming requests are blocked because --allow-arm is omitted; mission events record arming_blocked",
        },
        {
            "step": 4,
            "id": "simulation_arm_executor",
            "command": "scripts\\start_mission_executor_sim_arm.bat",
            "launches_gui": True,
            "read_only": False,
            "arms_vehicle": True,
            "requires_operator_confirmation": True,
            "expected_result": "simulation-only arm gate is used after read-only and no-arm smoke checks pass",
        },
    ]


def build_runbook(project_root, env_template_path, live_config_path, plan_path):
    env = complete_env(parse_env_template(env_template_path), project_root)
    validate_env(env)
    live_config = read_json(live_config_path)
    validate_live_config(live_config)
    plan = read_json(plan_path)
    validate_plan(plan)

    return {
        "stage": "stage6c_live_dual_mavros_smoke",
        "purpose": "Operator-facing live smoke sequence for dual-MAVROS readiness before simulation arming.",
        "generated_from": {
            "env_template": rel(env_template_path, project_root),
            "live_config": rel(live_config_path, project_root),
            "plan": rel(plan_path, project_root),
        },
        "environment": build_environment(env),
        "uavs": [
            {
                "uav_id": uav["uav_id"],
                "namespace": uav["namespace"],
                "state_topic": uav["state_topic"],
                "odom_topic": uav["odom_topic"],
                "set_mode_service": uav["set_mode_service"],
                "arming_service": uav["arming_service"],
            }
            for uav in live_config["uavs"]
        ],
        "safety_gates": {
            "run_read_only_smoke_before_executor": True,
            "run_no_arm_executor_before_simulation_arm": True,
            "simulation_arm_requires_operator_confirmation": True,
            "real_hardware_auto_arm_allowed": False,
        },
        "sequence": build_sequence(project_root, env, live_config, plan_path),
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate Stage 6C live dual-MAVROS smoke runbook")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--env-template", required=True, type=Path)
    parser.add_argument("--live-config", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        runbook = build_runbook(args.project_root, args.env_template, args.live_config, args.plan)
        write_json(args.output, runbook)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





