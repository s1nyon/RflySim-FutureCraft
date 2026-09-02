# Official Asset Metadata Calibration Runbook

## Scope

This workflow generates and checks the official-asset calibration scene, then
optionally records RflySim `PosUE`, `boxOrigin`, and `BoxExtent`. It does not
measure LiDAR, RGB, collision, dynamic motion, or role suitability. It never
authorizes OFFBOARD, arming, takeoff, flight, stack startup, or stack shutdown.

The committed candidate IDs are `13000..13009`; the reserved calibration-owned
range is `13000..13099`. Placement and removal act only on the ten declared IDs.

## Offline Validation and Generation

Run from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py generate --catalog config\calibration\official_asset_candidates_v1.json --output generated\calibration\official_assets_v1
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py load --catalog config\calibration\official_asset_candidates_v1.json
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py record --catalog config\calibration\official_asset_candidates_v1.json --output logs\calibration\20260813T120000Z_metadata
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py remove --catalog config\calibration\official_asset_candidates_v1.json
```

The last three commands are DryRuns because `--execute` is absent. They print
the exact IDs and catalog checksum without creating a UE client. DryRun record
does not create the output directory.

Review these generated files before any live action:

- `generated/calibration/official_assets_v1/calibration_preview.svg`
- `generated/calibration/official_assets_v1/resolved_scene.json`
- `generated/calibration/official_assets_v1/declared_profiles.json`
- `generated/calibration/official_assets_v1/validation_report.json`
- `generated/calibration/official_assets_v1/artifact_manifest.json`

Every initial profile must remain `DECLARED`; `approved_roles` and
`measurements` must be empty.

## Controlled T1 Metadata Checkpoint

Do not run this section during ordinary implementation. It changes the current
RflySim scene and requires an already healthy intended RflySim instance plus
operator review. It does not grant permission to start or stop the live stack.

1. Inspect the current stack and confirm the intended RflySim window and
   instance. Unknown or stale ownership fails closed.
2. Review the `load` DryRun. Confirm IDs `13000..13009`, official ClassIDs,
   positions, scales, `map_change=false`, and `arming_request=false`.
3. Obtain user approval for live placement when a healthy instance is not
   already explicitly in scope.
4. Place the ten declared objects:

   ```powershell
   D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py load --catalog config\calibration\official_asset_candidates_v1.json --window-id 0 --execute
   ```

5. Visually confirm that objects occupy only the calibration zone and that the
   active map did not change.
6. Record five metadata samples per candidate:

   ```powershell
   D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py record --catalog config\calibration\official_asset_candidates_v1.json --output logs\calibration\20260813T120000Z_metadata --samples 5 --timeout-s 10 --run-id 20260813T120000Z_metadata --stack-instance-id operator-confirmed-instance --execute
   ```

7. Review every profile. Only `METADATA_MEASURED` and `REJECTED` are valid
   states at this phase. A nonzero record exit preserves all profiles and means
   at least one candidate was rejected.
8. Review the `remove` DryRun, then remove only the declared IDs:

   ```powershell
   D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py remove --catalog config\calibration\official_asset_candidates_v1.json --window-id 0 --execute
   ```

9. Verify IDs `13000..13009` disappeared. Do not scan or remove the rest of the
   reserved range and do not clear the scene.

## Evidence Interpretation

- `DECLARED`: configuration and offline geometry only.
- `METADATA_MEASURED`: bounded live object-query samples were stable.
- `REJECTED`: metadata was missing, stale, malformed, or inconsistent.

This phase cannot produce `LIDAR_MEASURED`, `RGB_MEASURED`, or `ROLE_APPROVED`.
It does not prove collision geometry, sensor visibility, dynamic behavior,
official-map equivalence, flight safety, or competition readiness.

## Near-Field Visual Showcase

Use this overlay when the distant calibration grid is not visible from the
normal development view. It keeps `SLAMScene` and the predicted course, places
only IDs `13000..13009` in two rows at ENU x `11/13 m`, and stays outside the
stationary UAV spawn exclusion. It never authorizes flight.

Generate and review the plan before loading:

```powershell
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py showcase-generate --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json --output generated\calibration\official_asset_showcase_v1
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py showcase-load --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json --window-id 0
```

The DryRun must report `map_change=false`, `arming_request=false`, exact IDs
`13000..13009`, `fit_ground=true`, and the measured/expected dimensions. Live
loading requires a current manifest-owned RflySim3D process, no unknown
suspicious process, `GUI_READY=true`, `COURSE_READY=true`, and `SLAMScene` in
the recorded command line. ROS/MAVROS failure blocks all flight work, but does
not block this bounded UE-only overlay when those GUI/course gates pass.

After review, load window 0 only:

```powershell
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py showcase-load --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json --window-id 0 --execute
```

Remove only the showcase IDs after visual confirmation:

```powershell
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py showcase-remove --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json --window-id 0 --execute
```

The next independent phase measures Mid360 and RGB behavior and tests the
ClassID 43 image mechanism. It must retain the same no-arm and owned-ID rules.
