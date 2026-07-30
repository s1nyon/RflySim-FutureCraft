# Stage 2 Safe Dual-UAV Spawn Positions Design

## Problem

The dual-UAV launcher currently supplies `(-0.1, -0.8)` and `(0.1, -0.8)`
to the RflySim/CopterSim launch path.  The 0.2 m lateral spacing resulted in
the two simulated vehicles overlapping in ChallengeMap.  The current y value
also places the visible spawn near the lower map boundary.

## Decision

Use two symmetric candidate spawn points farther apart and farther into the
visible interior:

| Vehicle | x (m) | y (m) | yaw (degrees) |
| --- | ---: | ---: | ---: |
| uav1 | -0.8 | -0.3 | 0 |
| uav2 | 0.8 | -0.3 | 0 |

Keep the existing `ChallengeMap`, vehicle numbering, namespaces, ports, and
all flight-control settings unchanged.  The project launcher remains the
only place that supplies these values to the generated reference SITL wrapper.

## Verification

Update the Stage 2 offline validator so its generated-wrapper expectation
matches the new values.  Run the Stage 2 validator and the launcher dry-run.
Then stop the current simulation, restart the dual-UAV stack, and inspect the
top-down ChallengeMap view: both vehicles must be visibly separate, inside
the navigable area, and clear of walls.  If the visual check fails, do not arm
or run a mission; adjust only these candidate coordinates and repeat the
restart-and-inspect check.
