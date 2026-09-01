# Competition Course V2 map acceptance

Date: 2026-09-01 (Asia/Shanghai)

Historical result: **MAP READY — SUPERSEDED BY FRESH STARTUP REGRESSION**

> Superseding evidence (2026-09-01): fresh stack
> `stack-20260901T091442Z-ff2e5d81` reported `COURSE_READY`, but visual inspection
> found the static tunnel absent and the moving obstacle at its native, incorrect
> dimensions. The transition receipt shows that all V2 IDs were destroyed immediately
> before same-ID creation. The asynchronous destroy queue could therefore remove the
> newly created static entities; the continuously updated pendulum survived, while its
> `sendUE4PosNew` updates discarded the configured scale. Offline fixes now add a
> destroy-drain barrier and preserve spec-derived scale on every motion update. This
> historical acceptance is retained, but **MAP READY is withdrawn until a fresh live
> map-only revalidation passes**.

Scope was deliberately limited to map geometry, RflySim scene loading and
no-arm sensor/localization observation. EGO, mission, OFFBOARD, takeoff and
landing were not started.

## Accepted definition

- Single source: `config/maps/competition_course_v2.json`
- Final spec SHA-256: `6ce845ddb7269898929acfd5be17a11c18e0f7eb79be11c873bbb09a94fd9b69`
- Spawns: UAV1 `(16,-0.7,0)`, UAV2 `(16,0.7,0)`, both yaw 0 degrees ENU
- Corridor widths: `1.5 / 1.4 / 1.5 m`; turn radii: `0.9 / 0.9 m`
- Static passable gaps: `1.225 / 1.150 m` against a `1.000 m` requirement
- Pendulum: Section A pivot `(22,0,2.4)`, 1.2 m length, ±30 degrees, 6 s period;
  predicted longest safe window `1.858 s`
- Landing: two pads at `(32,3.9)` and `(32,5.9)`, ArUco IDs 31/47

The dynamic obstacle was moved from the occluded final section to the rear of
Section A after the first no-arm point probe produced 0/78 observations at its
old location. This preserves the declared pendulum geometry and corridor
semantics while making its motion testable from both accepted stationary spawn
poses.

## Offline verification

`scripts/validate_competition_course_v2.ps1` passed all twelve focused checks,
including schema/geometry, passability, deterministic ENU→NED position and yaw,
non-unit SDK scale, preview, loader, motion and entrypoint contracts. The
validator also caught no route self-intersections and a minimum route envelope
width of 1.4 m against the 0.95 m vehicle envelope.

The preview is `generated/competition_course_v2/course_preview.svg` (PNG render
beside it). It was visually checked for spawn/yaw/camera arrows, continuous
line-arc-line-arc-line corridor, wall openings, obstacle footprints and sweep,
landing area and top-facing ArUco boards.

## Map-only live verification

Stack `stack-20260831T173615Z-6d6e09b6`, simulation instance
`px4-2e845542d17999d3`, was started explicitly with
`-Course competition_course_v2`. No arming request was issued.

The first SDK metadata inspection exposed a map-layer defect: RflySim Class
`1000813` is natively `1×1×3 m`, while the loader had sent requested metre
dimensions directly as SDK scale. This made every requested Z dimension three
times too large. The spec now declares native asset size, the manifest retains
requested size and computes scale, and loader/transform tests exercise the
actual SDK request boundary.

After exact-ID reload, the final bounded SDK probe observed all 42 expected
objects (40 map entities plus two vehicles), with no missing IDs, position
errors or dimension errors. Spawn XY/yaw and resting-airframe height were also
checked. The pendulum metadata recorded 129 samples across a full
`y=-0.5999..+0.5999 m`, `z=1.2000..1.3607 m` sweep.

Key run artifacts:

- `logs/live_stack/stack-20260831T173615Z-6d6e09b6/map_acceptance/rflysim_entity_acceptance.json`
- `logs/live_stack/stack-20260831T173615Z-6d6e09b6/map_acceptance/rflysim_dynamic_metadata.json`
- `generated/competition_course_v2/load_receipt.json`

## No-arm sensor acceptance

Stage 7 run `stage7-20260831T174824Z-3749` used explicit `sensor-mode full`.
Readiness passed freshness, identity, isolation, schema and stationary-stability
gates with no errors. Final MAVROS evidence records both vehicles connected,
`armed: false`, `guided: false`, `mode: MANUAL`.

| Stream | UAV1 | UAV2 |
| --- | ---: | ---: |
| RGB | 8.89 Hz | 8.49 Hz |
| adapted LiDAR | 9.85 Hz | 10.24 Hz |
| IMU | 114.14 Hz | 116.71 Hz |
| Faster-LIO odometry | 10.02 Hz | 10.02 Hz |
| Faster-LIO registered cloud | 9.99 Hz | 10.17 Hz |

The final 78-frame geometry probe measured both Section A walls, the static box
and the moving obstacle. Static-box regions contained 57–83 UAV1 points and
32–45 UAV2 points per frame. Dynamic sweep regions contained 50–75 UAV1 points
and 45–72 UAV2 points; visible point centroids moved by about 0.30 m from each
side while SDK truth completed the full 1.20 m sweep. The two RGB images are
mirror-consistent with the parallel spawn arrangement and show the shared
entrance geometry and forward obstacle. Landing markers are around two turns,
so spawn cameras are not expected to see them; their top-facing accessibility
is established by the preview plus live entity pose, not by claiming detection.

Final sensor evidence:

- `logs/live_stack/stack-20260831T173615Z-6d6e09b6/map_acceptance/sensor_probe_final/report.json`
- `logs/live_stack/stack-20260831T173615Z-6d6e09b6/map_acceptance/lidar_geometry_report_final.json`
- `logs/live_stack/stack-20260831T173615Z-6d6e09b6/map_acceptance/mavros_state_final.txt`
- `logs/stage7_live/stage7-20260831T174824Z-3749/sensor_readiness.json`

The probe expected the two EGO PositionCommand topics only to demonstrate their
absence: both were `NOT_ADVERTISED`, as required for this map-only milestone.

## Boundary

This evidence does not establish navigation, replanning, target recognition,
ArUco decoding or landing. It creates no shared-world TF and changes no EGO,
Faster-LIO, mission, controller, lifecycle or arming policy. The next stage is
Competition Course V2 Navigation Baseline.

## Live stack handoff

The acceptance stack remains running at handoff. The final read-only lifecycle
inspection found no unknown suspicious process and no port owned by an unknown
process, but it fail-closed on one stale/reused Windows PID formerly recorded as
VcXsrv. `live_stack_stop.ps1 -DryRun` therefore refused that PID and reported
`clean: false`. No `-Execute`, force retry, PID sweep or lifecycle modification
was attempted; real stop remains a Red-Zone operation requiring explicit user
authorization. This operational handoff does not change the completed map and
sensor observations above, but a clean stack stop is not claimed by this record.
For the same reason, the repository-wide validator passed its static checks but
failed its live-stack dispatch/inspect step; focused V2, Stage 7, Stage 8 and
documentation-link validations all passed.
