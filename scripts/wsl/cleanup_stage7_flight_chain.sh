#!/usr/bin/env bash
# Keep this script LF-only for WSL execution.
#
# Clean the Stage 7 flight chain (sensor bridges, FAST-LIO, EGO planner,
# traj_server, waypoint generators, slam nodes, relays/adapters) that survives
# a flight run. These processes are spawned by the registered
# stage7_live_*_dual.sh / flight runner sessions but their roslaunch CHILDREN
# are not individually registered in the stack manifest, so the lifecycle stop
# would otherwise fail-closed on them as unknown.
#
# Safety:
#   - explicit PIDs only (pgrep -> kill loop; NO pkill, no name-scan kill)
#   - detection is limited to project flight-chain command lines (paths under
#     future_aircraft_sim / 28com_uav / ego-planner-swarm devel plus node names)
#   - `--dry-run` lists matching PIDs without killing
#   - NEVER touches stage2/mavros/px4 (handled by the lifecycle stop itself)
set -u

PATTERN='sensor_bridge|rflysim_fastlio|rflysim_ego_swarm|ego_planner_node|traj_server|stage7_live_fastlio|stage7_live_ego|stage7_live_slam|rflysim_pointcloud_adapter|rflysim_imu_relay|rflysim_depth_relay|rflysim_rgb_relay|rflysim_bottom_relay|uav1/slam|uav2/slam|laserMapping|odom_frame_relay|run_mapping_online|static_transform_publisher|waypoint_generator'

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

pids=$(pgrep -f "$PATTERN" 2>/dev/null || true)
if [ -z "$pids" ]; then
  echo "[cleanup] no stage7 flight-chain processes found"
  exit 0
fi

echo "[cleanup] matching flight-chain pids: $pids"
for p in $pids; do
  cmd=$(ps -p "$p" -o args= 2>/dev/null || true)
  echo "[cleanup] pid=$p cmd=${cmd:0:120}"
  if [ "$DRY_RUN" = false ]; then
    kill -KILL "$p" 2>/dev/null || true
  fi
done

sleep 2
left=$(pgrep -f "$PATTERN" 2>/dev/null || true)
if [ -z "$left" ]; then
  echo "[cleanup] CLEAN"
else
  echo "[cleanup] LEFT=$left"
  exit 1
fi
