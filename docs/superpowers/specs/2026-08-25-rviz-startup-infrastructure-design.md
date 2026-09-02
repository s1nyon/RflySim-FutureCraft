# RViz and Startup Infrastructure Design

Date: 2026-08-25

## Goal

Add optional, truthful per-UAV RViz debugging and shorten the protected live startup only where an observable readiness predicate can replace a fixed wait. Preserve PBL-1 behavior, ownership, manifest, stop, launch order, mission, and coordinate mathematics.

## Constraints

- `uav1_camera_init` and `uav2_camera_init` remain independent localization origins.
- No shared `competition_world` or cross-UAV transform is introduced.
- RViz is standalone, off by default, outside every READY/health/control dependency.
- Visualization adapters may relabel low-bandwidth visualization messages only. They do not modify control topics or numeric coordinates.
- Startup changes extend the existing lifecycle/readiness path. They do not redesign ownership, manifests, stop semantics, or upstream PX4/MAVROS/Faster-LIO/EGO.
- Every readiness timeout remains fail-closed. A timeout is not treated as an unconditional wait.

## RViz Architecture

`rflysim_rviz.launch` accepts `rviz_mode:=uav1|uav2|dual`. It launches one RViz process for each selected UAV with separate project-owned configuration:

- UAV1 fixed frame: `uav1_camera_init`
- UAV2 fixed frame: `uav2_camera_init`
- dual mode: two independent RViz processes; no common scene or origin

Each view consumes existing per-UAV odometry and adapted LiDAR topics. A small visualization-only adapter runs only with the standalone RViz launch. It builds a bounded path from relayed odometry and republishes low-bandwidth EGO goal/trajectory markers with the verified per-UAV localization label while preserving their points, poses, timestamps, and other fields. It does not relay the high-bandwidth registered cloud. EGO occupancy and ground truth remain disabled unless a later live audit proves a truthful, low-risk display contract.

RViz process failure is isolated because the launch is never included by the protected `sim.ps1 start` or Stage 7 launch path.

## Startup Measurement

Before changing startup, perform three RViz-off fresh starts. For each run, derive stage timestamps from the stack manifest, health JSON, lifecycle traces, Stage 7 context/readiness report, and an explicit timing collector. Store ignored JSON/Markdown under `logs/startup_timing/<run>/`.

The timing model records command start, GUI/process availability, ROS master, MAVROS connections, course load, sensor valid messages, Faster-LIO odometry, MAVROS local-position feedback, EGO role/topic readiness, and overall ready. Each stage includes predicate, timeout, result, and elapsed time. Missing evidence is reported as unknown rather than inferred from process existence.

## Startup Optimization

Audit candidates are handled as follows:

1. Replace the unconditional 30-second SITL boot wait with a bounded predicate that proves both PX4 instance sockets/functional link prerequisites are available before starting MAVROS.
2. Replace fixed per-instance MAVLink-link sleeps and MAVROS stagger sleeps only if the existing command/socket/state predicates can prove readiness.
3. Replace the post-EGO fixed two-second survival delay with a bounded role/topic readiness check.
4. Retain the 10-second scene wait if no reliable pre-load acknowledgement exists. Course-load success remains a health predicate; actual sensor messages remain the later scene-content proof.
5. Preserve polling intervals and bounded timeouts where they already implement fail-closed readiness rather than unconditional delay.

The smallest implementation may add a pure-Python polling/timing helper plus thin PowerShell/Bash wrappers. Tests cover immediate success, delayed success, timeout, invalid data, process-only false positives, and elapsed-time reporting.

## Validation

Offline validation precedes all live work: focused tests, launch XML/static checks, package build, lifecycle, Stage 7, Stage 8, repository, and docs checks.

Live validation uses the manifest lifecycle exclusively:

- three RViz-off baseline startup measurements;
- per-UAV and dual RViz functional validation plus one RViz-off/on frequency comparison;
- three RViz-off fresh startup measurements after optimization;
- two fresh full existing-route regressions with OFFBOARD, landing/disarm, zero collision, zero offboard loss, and zero timeout;
- standard clean stop and ownership verification after every run.

Any unexplained intermittent startup failure, degraded health gate, stop-clean failure, or flight regression blocks further changes.

## Rollback

RViz is removed by reverting its standalone launch/config/adapter commit. Startup optimization is independently reverted by its lifecycle commit. Neither rollback changes mission or external dependency state.
