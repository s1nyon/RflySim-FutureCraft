# Faster Tandem Tunnel Flight Design

## Goal

Increase the protected tunnel-flight speed while making UAV2 follow UAV1 through
the tunnel at a nominal 1.1 m separation (about 2.4 vehicle diameters). UAV1 must
enter first; both vehicles retain the existing route, safety gates, geofence, and
landing behavior.

## Design

- Raise the dual EGO-Swarm defaults from 0.3 m/s and 0.5 m/s^2 to 0.6 m/s and
  0.8 m/s^2.
- Sample the existing course centreline at no more than 1.1 m spacing, preserving
  line and arc geometry rather than cutting corners.
- Generate a pipelined plan: UAV1 receives sample `n+1` before UAV2 receives
  sample `n`; verification follows both publications. This keeps UAV1 one sample
  ahead while allowing both planners to move concurrently.
- Keep separate landing-platform goals after the shared tunnel samples.
- Do not change PX4, EGO core, watchdog, geofence, arming, or lifecycle behavior.

## Validation

Use the existing Stage 8 plan contract, extended to assert speed defaults,
centreline sampling, UAV1-first dispatch, and nominal 0.9-1.35 m route spacing.
Run only this focused contract for the requested fast turnaround.
