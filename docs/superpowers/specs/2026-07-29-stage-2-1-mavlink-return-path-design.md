# Stage 2.1 MAVLink Return-Path Validation Design

> **Historical note, 2026-07-30:** This design's `16540/17540` FCU URL was superseded by the dedicated MAVROS links validated against the GUI simulation: `/uav1` `udp://:14601@127.0.0.1:14600`, `/uav2` `udp://:14611@127.0.0.1:14610`. The old ports belong to the Rfly SIL/CopterSim path and must not be restored as MAVROS URLs.

## Scope

Stage 2.1 turns the unresolved MAVROS `connected: false` problem into a bounded, single-UAV validation stage. It verifies the MAVLink return path from PX4 to MAVROS before the project resumes dual-UAV startup, Stage 6D no-arm smoke, or any simulation arming flow.

This stage does not change flight behavior, target detection, behavior-tree contracts, namespaces, or Stage 5 event output. It does not modify `28com_uav`, PX4 Firmware, RflySim3D, or CopterSim.

## Evidence and Problem Statement

The failed dual-UAV run established the following local facts:

- Both PX4 instances started and reported the generated Rfly offboard links: `17540 -> 16540` for UAV 1 and `17541 -> 16541` for UAV 2.
- Both MAVROS nodes bound their configured receive ports and sent MAVLink traffic to PX4.
- PX4 recorded valid GCS heartbeats and nonzero received MAVROS traffic.
- MAVROS continued to publish `connected: false` and no local-position odometry.

The failure is therefore treated as a PX4-to-MAVROS return-path problem until a fresh Stage 2.1 report proves otherwise. Process existence, service registration, and a configured FCU URL are insufficient proof of an end-to-end ROS flight-control link.

## Architecture

Stage 2.1 introduces a project-owned, single-UAV live verifier with three sequential gates:

```text
single-UAV simulator / PX4 startup
    -> PX4 runtime evidence: generated ports, TX/RX counters, partner address
    -> MAVROS runtime evidence: connected state, local odometry, services
    -> Stage 2.1 JSON report
    -> pass: enable the existing dual-UAV Stage 2 gate
    -> fail: stop; do not run Stage 6D or any arming path
```

The verifier must target `/uav1` first. It may start or reuse the project-owned single-UAV launch path, but it must never issue `set_mode`, `cmd/arming`, or position setpoints. A later dual-UAV verifier reuses the same checks separately for `/uav1` and `/uav2`.

## Components

### Single-UAV launcher and verifier

Add a Stage 2.1 runner under `scripts/` plus a WSL helper under `scripts/wsl/`. The runner has a dry-run mode and a live mode. Live mode writes all artifacts beneath `logs/stage2_1_live/` and exits nonzero on any failed gate.

The WSL helper sources ROS Noetic and the existing reference workspace exactly as the current MAVROS launchers do. It gathers evidence without editing installed toolchain files.

### Runtime evidence collector

The collector records:

- effective MAVROS FCU URL, namespace, and process/log location;
- the PX4 instance output lines that identify MAVLink local/remote ports, partner address, and TX/RX rates or counters;
- one `mavros/state` sample and one `mavros/local_position/odom` sample attempt;
- visibility of the `set_mode` and `arming` services, recorded only as availability checks.

The report stores evidence values and a normalized status; it does not infer success from a process list alone.

### Classification

The verifier returns one of these explicit statuses:

- `ready`: PX4 has a live MAVLink link, MAVROS is connected, odometry is received, and required services are visible.
- `px4_not_started`: no current PX4 instance evidence is found.
- `mavros_not_started`: the expected MAVROS node or state topic is absent.
- `px4_to_mavros_return_path_blocked`: PX4 received MAVROS traffic or a valid GCS heartbeat, while MAVROS remains disconnected or odometry is absent.
- `mavros_to_px4_path_blocked`: MAVROS is running but PX4 reports no matching incoming MAVLink evidence.
- `inconclusive`: required log/counter evidence cannot be collected.

The classification is intentionally conservative: only `ready` permits escalation to the dual-UAV gate.

## Interfaces and Artifacts

The live report uses a stable JSON schema under `logs/stage2_1_live/mavlink_link_report.json`:

```json
{
  "stage": "2.1",
  "uav_id": "uav1",
  "namespace": "/uav1",
  "status": "px4_to_mavros_return_path_blocked",
  "mavros": {
    "fcu_url": "udp://:16540@127.0.0.1:17540",
    "connected": false,
    "odom_received": false,
    "set_mode_service": true,
    "arming_service": true
  },
  "px4": {
    "mavlink_local_port": 17540,
    "mavlink_remote_port": 16540,
    "partner_ip": "127.0.0.1",
    "received_mavros_traffic": true
  },
  "evidence_paths": []
}
```

The exact report can include additional non-breaking metadata such as timestamps and log paths. Stage 2, Stage 5, and Stage 6 contracts remain unchanged.

## Error Handling and Safety

- Live verification has a bounded timeout for each ROS sample and records timeout details in the report.
- Any missing process, log, topic, service, or malformed PX4 status output yields a classified non-ready result rather than a silent pass.
- The verifier must not invoke MAVROS services, publish flight setpoints, change flight modes, or arm any vehicle.
- Stage 6D and Stage 6E remain blocked until the dual-UAV extension records `ready` for both namespaces.
- Existing user changes remain untouched; all implementation changes are project-local.

## Testing and Acceptance

Offline validation must verify report parsing, classification, dry-run output, and rejection of incomplete evidence. It must not launch WSL GUI applications, RflySim3D, CopterSim, PX4, ROS, or MAVROS.

Live acceptance for single UAV requires all of the following in one fresh report:

1. PX4 reports the effective MAVLink local and remote port pair and receives MAVROS traffic.
2. MAVROS reports `connected: true`.
3. `/uav1/mavros/local_position/odom` publishes a message.
4. `/uav1/mavros/set_mode` and `/uav1/mavros/cmd/arming` are visible, without being called.

Only after this result is repeatable can the same verifier be extended to `/uav2`. The existing Stage 6D no-arm smoke is then the next live gate; Stage 6E remains outside this stage.

## Non-Goals

- No direct MAVLink control client is introduced as a MAVROS replacement.
- No real camera or detector integration is attempted.
- No PX4 Firmware, RflySim3D, CopterSim, or reference-project source is patched.
- No simulation or real-aircraft arming is performed.
