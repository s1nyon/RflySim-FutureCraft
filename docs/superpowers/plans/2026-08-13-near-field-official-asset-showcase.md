# Near-Field Official Asset Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and live-load a bounded, visually obvious two-row showcase of ten official RflySim assets near the UAV spawn area, with correct static metadata sampling and deterministic cleanup.

**Architecture:** Add a dedicated showcase catalog and pure geometry/resolution module while reusing the existing official-asset catalog and owned-ID loader. Correct metadata freshness at the sampling boundary, close the vendor receiver explicitly, expose DryRun-first showcase commands, then load only after current manifest ownership and GUI/course readiness are proven.

**Tech Stack:** Python 3.8, standard library JSON/dataclasses/statistics, RflySim `UE4CtrlAPI`, PowerShell validators, existing plain-Python contract tests.

## Global Constraints

- Use only official assets already declared in `official_asset_candidates_v1.json`.
- Mutate only IDs `13000..13009` in RflySim window 0; never clear or change the map.
- Preserve predicted-course IDs `12000..12999` and both stationary UAVs.
- No mission, OFFBOARD, arming, takeoff, or flight.
- Showcase centers are ENU x=`11.0/13.0` m and y=`-5.0/-2.5/0.0/2.5/5.0` m.
- Uniform scale targets longest edge `1.2 m`, except Pillar height `1.5 m`, clamped to `[0.02,2.0]`.
- Live placement uses the official fit-ground API.
- Equal vendor timestamps are valid when local receipt times are fresh; decreasing timestamps are rejected.
- Generated artifacts remain ignored; live evidence remains under ignored `logs/calibration/`.

---

### Task 1: Correct Static Metadata Sampling and Receiver Shutdown

**Files:**
- Modify: `scripts/calibration/object_metadata.py`
- Modify: `scripts/calibration/calibration_cli.py`
- Modify: `tests/asset_calibration_metadata_check.py`
- Modify: `tests/asset_calibration_cli_check.py`

**Interfaces:**
- Produces: `close_metadata_receiver(client) -> None`
- Changes: `analyze_samples(...)` permits equal vendor timestamps, rejects decreasing timestamps, and validates increasing local receipt times.
- Changes: `_record(...)` always closes the receiver in `finally`.

- [ ] **Step 1: Add failing static timestamp and shutdown contracts**

Add metadata assertions using three samples whose vendor timestamp is `10.0` while `received_at_unix_s` increases; expect `METADATA_MEASURED`. Add a decreasing `10.0,9.9,10.1` case expecting `DECREASING_VENDOR_TIMESTAMPS`. Give fake clients `endUE4MsgRec()` and assert one initialization and one shutdown for success and all-timeout runs.

- [ ] **Step 2: Run focused tests and observe the intended failures**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_metadata_check.py --catalog-module scripts\calibration\asset_catalog.py --geometry-module scripts\calibration\calibration_geometry.py --metadata-module scripts\calibration\object_metadata.py --catalog config\calibration\official_asset_candidates_v1.json
D:\PX4PSP\Python38\python.exe tests\asset_calibration_cli_check.py --cli scripts\calibration\calibration_cli.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL on equal timestamps and/or missing receiver shutdown.

- [ ] **Step 3: Implement minimal sampling and cleanup changes**

Use `second < first` for vendor time rejection; require `second > first` for local receipt times; rename the reason to `DECREASING_VENDOR_TIMESTAMPS`; call `client.endUE4MsgRec()` when available from a `finally` around the complete candidate loop.

- [ ] **Step 4: Re-run focused tests**

Expected: both focused checks PASS and the process exits normally.

- [ ] **Step 5: Commit**

```powershell
git add scripts/calibration/object_metadata.py scripts/calibration/calibration_cli.py tests/asset_calibration_metadata_check.py tests/asset_calibration_cli_check.py
git commit -m "fix: support static asset metadata sampling"
```

### Task 2: Define and Resolve the Near-Field Showcase

**Files:**
- Create: `config/calibration/official_asset_showcase_v1.json`
- Create: `scripts/calibration/showcase_geometry.py`
- Create: `tests/asset_showcase_geometry_check.py`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: `load_catalog(path) -> CalibrationCatalog`, `Vec3`, and measured full dimensions keyed by candidate key.
- Produces: `ShowcaseSpec`, `ShowcasePlacement`, `load_showcase(path)`, `resolve_showcase(spec, catalog)`, and `validate_showcase(placements, spawn_centers, exclusion_radius_m)`.

- [ ] **Step 1: Write the failing showcase geometry contract**

Assert exact IDs, two-by-five station centers, uniform scales, target longest edges, scale clamp, pairwise non-overlap, and at least 3 m x separation from spawn centers `(16,-0.7)` and `(16,0.7)`. Assert unknown keys, duplicate stations, non-finite dimensions, and IDs outside `13000..13009` fail closed.

- [ ] **Step 2: Run the geometry contract and observe missing-module failure**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_showcase_geometry_check.py --catalog-module scripts\calibration\asset_catalog.py --showcase-module scripts\calibration\showcase_geometry.py --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json
```

Expected: FAIL because the showcase module/spec do not exist.

- [ ] **Step 3: Add the measured showcase spec and pure resolver**

Store measured full dimensions from `t1-debug-20260812T180649Z` with provenance state `EXPLORATORY_T1`. Resolve scale as `min(max(target/max_dimension,0.02),2.0)`, except Pillar uses `1.5 / measured_z`. Preserve official ClassID and variant from the base catalog; never grant approved roles.

- [ ] **Step 4: Run the geometry contract**

Expected: PASS with ten resolved placements and no spawn/placement conflicts.

- [ ] **Step 5: Classify new scripts and commit**

Add the module to the Protected internal table and the test to the repository's test inventory conventions, then commit:

```powershell
git add config/calibration/official_asset_showcase_v1.json scripts/calibration/showcase_geometry.py tests/asset_showcase_geometry_check.py scripts/README.md
git commit -m "feat: define near-field asset showcase"
```

### Task 3: Generate Artifacts and Add DryRun-First Showcase Commands

**Files:**
- Create: `scripts/calibration/showcase_artifacts.py`
- Create: `tests/asset_showcase_artifacts_check.py`
- Create: `tests/asset_showcase_cli_check.py`
- Modify: `scripts/calibration/calibration_cli.py`
- Modify: `scripts/calibration/ue_asset_loader.py`
- Modify: `scripts/validate_asset_calibration.ps1`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: resolved `ShowcasePlacement` values.
- Produces: `generate_showcase_artifacts(...)`, `place_showcase(...)`, and CLI commands `showcase-generate`, `showcase-load`, `showcase-remove`.

- [ ] **Step 1: Write failing artifact and CLI contracts**

Assert deterministic SVG/JSON/manifest output. Assert DryRun prints IDs, ClassIDs, ENU/NED positions, uniform scales, measured/expected dimensions, `map_change=false`, and `arming_request=false`, without importing `UE4CtrlAPI`. Assert execute placement calls `sendUE4PosScale2Ground` three times per declared ID for window 0; removal calls `sendUE4Destroy` only for `13000..13009`.

- [ ] **Step 2: Run focused contracts and observe missing-feature failures**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_showcase_artifacts_check.py --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json
D:\PX4PSP\Python38\python.exe tests\asset_showcase_cli_check.py --cli scripts\calibration\calibration_cli.py --catalog config\calibration\official_asset_candidates_v1.json --showcase config\calibration\official_asset_showcase_v1.json
```

Expected: FAIL because showcase commands and artifacts are missing.

- [ ] **Step 3: Implement artifacts, bounded loader, and CLI dispatch**

Keep generic existing load/remove behavior unchanged. Showcase commands accept both `--catalog` and `--showcase`; `showcase-load/remove` remain DryRun without `--execute`; only `showcase-load --execute` imports the UE client and calls the fit-ground API.

- [ ] **Step 4: Extend the public validator and run it**

Add the three new focused checks plus showcase load/remove DryRuns to `validate_asset_calibration.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
```

Expected: all asset calibration and showcase checks PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/calibration/showcase_artifacts.py scripts/calibration/calibration_cli.py scripts/calibration/ue_asset_loader.py scripts/validate_asset_calibration.ps1 scripts/README.md tests/asset_showcase_artifacts_check.py tests/asset_showcase_cli_check.py
git commit -m "feat: add visible asset showcase workflow"
```

### Task 4: Document, Review, and Live-Load the Showcase

**Files:**
- Modify: `docs/runbooks/official-asset-metadata-calibration.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: showcase CLI and current manifest inspection.
- Produces: operator commands and fresh ignored live artifacts.

- [ ] **Step 1: Update the runbook**

Document the near-field distinction, exact station region, fit-ground behavior, DryRun review, manifest ownership check, visual confirmation, metadata recording, and exact-ID cleanup. State that ROS/MAVROS failure blocks flight but a current `GUI_READY=true` and `COURSE_READY=true` may authorize this UE-only no-arm overlay.

- [ ] **Step 2: Run full offline validation**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 3: Perform read-only live gates**

Inspect `logs/live_stack/stack-20260812T180404Z-61a0a1eb/stack_manifest.json`; require owned live RflySim3D, zero unknown suspicious processes, `GUI_READY=true`, `COURSE_READY=true`, and map command line `SLAMScene`. Run showcase-load DryRun and review all ten commands.

- [ ] **Step 4: Execute bounded live load and collect metadata**

Run `showcase-load --window-id 0 --execute`, then record five samples using a fresh run ID and the exact stack ID. Do not run FAST-LIO, EGO, mission, OFFBOARD, or arming. Report the visual confirmation checkpoint to the user.

- [ ] **Step 5: Commit documentation, request code review, and hand off**

```powershell
git add docs/runbooks/official-asset-metadata-calibration.md docs/README.md
git commit -m "docs: add near-field showcase runbook"
```

Use `requesting-code-review`, fix Critical/Important findings, and re-run Task 4 Step 2. Keep the showcase loaded for user visual confirmation; cleanup remains the explicit `showcase-remove --window-id 0 --execute` command after confirmation.
