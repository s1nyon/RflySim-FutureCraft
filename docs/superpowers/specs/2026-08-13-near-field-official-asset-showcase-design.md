# Near-Field Official Asset Showcase Design

## Purpose

Make the official RflySim asset calibration work visually obvious before any
candidate is integrated into the predicted competition course. The showcase is
a temporary, no-arm overlay on `SLAMScene`; it is not a replacement competition
map and does not establish role suitability.

## Runtime Boundary

- Use only the official candidates already declared in
  `official_asset_candidates_v1.json`.
- Own and mutate only object IDs `13000..13009` in RflySim window 0.
- Do not change the active map, clear the scene, start a mission, enter
  OFFBOARD, arm, or move either UAV.
- Keep the predicted course IDs `12000..12999` untouched.
- Use the manifest-owned live RflySim instance only. A failed ROS/MAVROS gate
  blocks flight work but does not invalidate a bounded UE-only showcase when
  `GUI_READY` and `COURSE_READY` are current and true.
- Removal is always an explicit ID list, never a name scan or scene clear.

## Layout

The showcase uses two rows of five stations near the two spawn vehicles so it
is visible from the normal development view. Its ENU station grid is:

```text
x = 11.0 m: y = -5.0, -2.5, 0.0, 2.5, 5.0 m
x = 13.0 m: y = -5.0, -2.5, 0.0, 2.5, 5.0 m
```

The current UAV spawn centers are near ENU `(16.0, -0.7)` and `(16.0, 0.7)`.
The nearest showcase center is therefore at least 3 m away in x. No showcase
station is used for flight while the overlay is loaded.

Each asset is scaled uniformly from its measured full bounding box. The
longest measured edge targets `1.2 m`, except the pillar, whose height may
target `1.5 m`. Scale is clamped to `[0.02, 2.0]`. The loader uses the official
fit-ground placement API so mesh-origin offsets do not require guessed z
coordinates. The DryRun prints source dimensions, selected uniform scale,
resolved ENU/NED pose, and expected scaled dimensions for every station.

The exploratory T1 measurements from run
`t1-debug-20260812T180649Z` seed the first showcase profile. They are retained
as live exploratory evidence, not committed as approved role evidence. A fresh
metadata pass replaces these seeds after the sampling defect is fixed.

## Metadata Sampling Correction

RflySim may repeatedly publish a static object's unchanged simulator timestamp.
That is valid for a stationary object and must not be labelled stale merely
because successive vendor timestamps are equal.

The recorder therefore:

- treats a decreasing vendor timestamp as invalid, but permits equality;
- proves freshness with the locally captured packet receipt times;
- requires strictly increasing local receipt times and a fresh final receipt;
- retains vendor timestamps unchanged in evidence;
- preserves partial samples and emits `REJECTED` for real timeout, malformed
  data, decreasing simulator time, or unstable position/extent;
- closes its UE receive socket/thread so a completed CLI process exits without
  external termination.

## Commands and Artifacts

Add a showcase catalog derived from measured geometry and extend the existing
DryRun-first CLI with bounded commands:

```powershell
calibration_cli.py showcase-generate --catalog <showcase.json> --output <dir>
calibration_cli.py showcase-load --catalog <showcase.json> [--window-id 0] [--execute]
calibration_cli.py showcase-remove --catalog <showcase.json> [--window-id 0] [--execute]
```

`showcase-load` and `showcase-remove` are DryRun unless `--execute` is present.
The generated artifacts include a plan-view SVG, resolved commands, dimension
table, validation report, and manifest. The live metadata output remains under
ignored `logs/calibration/<run-id>` and is never promoted automatically.

## Verification and Acceptance

Offline acceptance requires:

1. IDs are exactly `13000..13009` and no command clears or changes the map.
2. Every station is outside the UAV spawn exclusion circles and pairwise
   separated after measured scaling.
3. Longest scaled edges satisfy the configured targets and clamp.
4. ENU/NED conversions and fit-ground calls match the official API contract.
5. Equal vendor timestamps pass when local receipt times are fresh; decreasing
   timestamps and stale receipts fail.
6. The metadata CLI terminates normally after success or rejection.
7. Existing asset, repository, Stage 7, and Stage 8 offline checks remain green.

Live acceptance is deliberately visual and bounded:

1. Review the exact DryRun receipt.
2. Load window 0 only and confirm ten visibly distinct objects appear near the
   spawn area while the base scene and predicted course remain unchanged.
3. Record fresh metadata and report each measured full size and ground offset.
4. Remove only IDs `13000..13009` and confirm the showcase disappears.

No result from this phase may be labelled `ROLE_APPROVED`, `RGB_MEASURED`,
`LIDAR_MEASURED`, collision-validated, or competition-ready.
