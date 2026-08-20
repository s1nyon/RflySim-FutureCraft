# Smoother Tunnel Waypoint Handoff Design

## Goal

Reduce the visible stop-and-go motion while both aircraft traverse the protected narrow-course map, without changing the route geometry, speed limits, tandem spacing, planner core, or safety boundaries.

## Evidence

Fresh live run `stage7-20260820T110453Z-2745` completed successfully and landed both aircraft, but took 68.5 seconds. The generated mission repeatedly publishes a centreline goal and waits until the aircraft is within 0.30 m before publishing the next goal. With centreline samples about 1.1 m apart, this makes EGO decelerate near every intermediate goal and produces the observed cadence.

## Design

For course-mode intermediate navigation only, increase `verify_planned_navigation.tolerance_m` from 0.30 m to 0.50 m. This hands the next goal to EGO while the aircraft is still moving. Keep the existing goal sampling, UAV1-first pipeline, takeoff, landing, watchdog, geofence, maximum velocity, and maximum acceleration unchanged.

The platform landing goals remain fully verified by the existing mission sequence; this change only affects when the executor advances between course goals.

## Risk and Rollback

The larger handoff radius may permit slightly more corner cutting. The selected 0.50 m remains below half the approximately 1.066 m sampled segment length, so each goal still requires meaningful forward progress. Rollback is a one-line restoration to 0.30 m.

## Validation

Run the focused Stage 8 course-flight-plan contract and Python compilation. Then rerun the existing live stack using a fresh readiness report and confirm successful navigation, landing, no collision/offboard loss, and visibly reduced waypoint hesitation.
