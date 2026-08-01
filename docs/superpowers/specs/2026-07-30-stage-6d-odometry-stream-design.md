# Stage 6D MAVLink Odometry Stream Design

## Problem

The Stage 6D read-only smoke check waits for
`/uav*/mavros/local_position/odom`.  The dedicated PX4-to-MAVROS links are
connected, but that topic times out for both vehicles.

`LOCAL_POSITION_NED` is not sufficient: MAVROS local-position uses it for
local pose and velocity.  Its `local_position/odom` publication requires
`LOCAL_POSITION_NED_COV`.  The installed PX4 MAVLink stream registry has no
`LOCAL_POSITION_NED_COV` stream, so requesting the existing stream cannot
produce the required topic.

PX4 does provide an `ODOMETRY` MAVLink stream.  MAVROS extras provides the
`OdometryPlugin`, whose FCU output is `mavros/odometry/in`; `mavros/odometry/out`
is the reverse input sent toward the FCU.

## Decision

Use the FCU's real `ODOMETRY` stream as the Stage 6D odometry readiness
interface.

- Keep `LOCAL_POSITION_NED` at 30 Hz for
  `/uav*/mavros/local_position/pose` and local velocity.
- Request `ODOMETRY` at 30 Hz on each dedicated PX4-to-MAVROS link.
- Configure the live mission contract to wait for
  `/uav*/mavros/odometry/in`, not `/uav*/mavros/local_position/odom`.
- Ensure the existing MAVROS launch loads the extras `odom` plugin; do not
  introduce a pose-to-odometry relay.

## Scope and Safety

Only project-local configuration, scripts, tests, fixtures, and documentation
may change.  Do not change Firmware, CopterSim, RflySim3D, or `28com_uav`.
The dedicated MAVROS links remain `14600/14601` and `14610/14611`; the Rfly
SIL ports remain untouched.

The Stage 6D checker remains read-only: it must not arm, set mode, or publish
FCU setpoints.  A fresh GUI restart is required before any live check.  Stage
6E remains prohibited until Stage 6D has a fresh passing live report.

## Verification

Before production changes, add a failing offline validation that requires the
two `ODOMETRY` stream requests and the new live odom topic contract.  Run it
to observe failure, then make the smallest changes needed for it to pass.
Run the existing Stage 2 and Stage 6D validators after the change.  A passing
offline check does not claim live success; live success requires a fresh,
no-arm Stage 6D report after restarting the GUI simulation.
