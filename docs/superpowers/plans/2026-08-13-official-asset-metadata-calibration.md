# Official Asset Metadata Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a no-arm, project-local calibration tool that validates an official-asset catalog, generates a deterministic metric calibration scene, safely loads only owned objects, records RflySim `PosUE`/`boxOrigin`/`BoxExtent`, and produces auditable metadata profiles.

**Architecture:** Keep calibration code in a new Agent-owned `scripts/calibration` package and leave the protected PBL-1 course and mission packages unchanged. Pure modules validate catalog/geometry and generate artifacts offline; thin UE adapters perform explicit live placement and read-only metadata capture. This plan ends at metadata calibration (T0/T1); LiDAR/RGB measurement, dynamic pendulum motion, image deployment, and predicted-course integration remain separate implementation plans.

**Tech Stack:** Python 3.8 standard library, RflySim `UE4CtrlAPI`, JSON, SVG, PowerShell validation wrappers, repository-style standalone Python contract tests.

## Global Constraints

- Use only assets and APIs distributed with the installed RflySim platform.
- Treat `D:\PX4PSP\RflySim3D`, general `RflySimAPIs` examples, CopterSim, PX4, and `28com_sim`/`28com_uav` as read-only.
- Do not modify PBL-1, `future_aircraft_ws/src/multi_uav_mission`, lifecycle internals, PX4, Faster-LIO, or EGO-Swarm.
- Do not send a map-change command, OFFBOARD request, arming request, takeoff request, or mission request.
- Create and destroy only object IDs in the calibration-owned range `13000..13099`.
- Default every state-changing entry to DryRun; live placement requires an explicit `--execute` flag.
- Do not edit or deploy `D:\PX4PSP\RflySim3D\RflySim3D\Content\Aruco\Aruco.png` in this plan.
- Store generated deterministic artifacts beneath `generated/calibration`; store run-scoped live evidence beneath `logs/calibration`.
- Do not mark any asset `LIDAR_MEASURED`, `RGB_MEASURED`, or `ROLE_APPROVED` in this plan.
- Preserve raw vendor coordinates and separately record converted project ENU values.
- All new `.py` and `.ps1` files are tracked scripts and must be classified exactly once in `scripts/README.md`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `config/calibration/official_asset_candidates_v1.json` | Declared official asset identities, scales, stations, owned IDs, and conservative bounds |
| `scripts/calibration/__init__.py` | Calibration package marker only |
| `scripts/calibration/asset_catalog.py` | Pure catalog parsing, validation, hashing, and immutable data types |
| `scripts/calibration/calibration_geometry.py` | Pure station overlap/boundary checks and ENU↔vendor coordinate conversion |
| `scripts/calibration/calibration_artifacts.py` | Deterministic resolved-scene JSON, declared-profile JSON, validation report, and SVG preview |
| `scripts/calibration/ue_asset_loader.py` | DryRun-first official API placement/removal for owned IDs only |
| `scripts/calibration/object_metadata.py` | Vendor sample normalization, stability analysis, profile state transitions, and metadata recording CLI |
| `scripts/calibration/calibration_cli.py` | Supported `generate`, `load`, `remove`, and `record` command dispatcher |
| `scripts/validate_asset_calibration.ps1` | Supported offline T0 validation entry |
| `tests/asset_calibration_catalog_check.py` | Catalog/schema and invalid-input contract tests |
| `tests/asset_calibration_geometry_check.py` | Coordinate, station, and overlap contract tests |
| `tests/asset_calibration_artifacts_check.py` | Deterministic output and SVG contract tests |
| `tests/asset_calibration_ue_loader_check.py` | Fake-client safety and DryRun contract tests |
| `tests/asset_calibration_metadata_check.py` | Sample normalization, stability, provenance, and profile-state tests |
| `tests/asset_calibration_cli_check.py` | End-to-end offline CLI and safety-language checks |
| `docs/runbooks/official-asset-metadata-calibration.md` | Exact DryRun/T1 procedure, artifacts, cleanup, and unsupported claims |
| `scripts/README.md` | Classify new public/internal scripts |
| `docs/README.md` | Link the runbook without making it Current Truth |

---

### Task 1: Candidate Catalog and Pure Validation

**Files:**
- Create: `config/calibration/official_asset_candidates_v1.json`
- Create: `scripts/calibration/__init__.py`
- Create: `scripts/calibration/asset_catalog.py`
- Create: `tests/asset_calibration_catalog_check.py`

**Interfaces:**
- Produces: `Vec3`, `AssetCandidate`, `CalibrationCatalog`, `CatalogValidationError`
- Produces: `load_catalog(path: Path) -> CalibrationCatalog`
- Produces: `catalog_sha256(path: Path) -> str`
- Produces: `profile_id(candidate: AssetCandidate) -> str`
- Consumes: JSON only; no RflySim imports and no filesystem writes except test fixtures

- [ ] **Step 1: Write the failing catalog contract test**

Create a standalone test that imports `asset_catalog.py`, loads the committed JSON, and asserts:

```python
catalog.schema_version == 1
catalog.frame == "ENU"
catalog.units == "m"
catalog.owned_id_range == (13000, 13099)
[asset.key for asset in catalog.assets] == [
    "pillar_813", "box_815", "box_818",
    "carton_500", "carton_750", "carton_1000",
    "ring_target_150", "quad_target_151",
    "aruco_custom_43", "luminous_light_60",
]
len({asset.object_id for asset in catalog.assets}) == len(catalog.assets)
all(13000 <= asset.object_id <= 13099 for asset in catalog.assets)
all(profile_id(asset).startswith(asset.key + "@") for asset in catalog.assets)
```

Use temporary JSON mutations to assert rejection of duplicate keys/IDs, ID outside the owned range, non-finite positions/scales, non-positive scale or conservative bounds, unknown roles, missing official source, station outside the zone, and schema version other than `1`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_catalog_check.py --module scripts\calibration\asset_catalog.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL because the module and catalog do not exist.

- [ ] **Step 3: Add the candidate catalog**

Use this top-level contract:

```json
{
  "schema_version": 1,
  "catalog_name": "official_asset_candidates_v1",
  "frame": "ENU",
  "units": "m",
  "base_map": "SLAMScene",
  "owned_id_range": [13000, 13099],
  "calibration_zone": {"bounds": [40.0, 58.0, -9.0, 9.0], "placement_z": 0.0},
  "station_clearance_m": 0.75,
  "assets": []
}
```

Give each candidate a stable `key`, unique `object_id`, numeric `class_id`, `official_source`, `variant`, `intended_roles`, `station.position`, `station.yaw_rad`, positive `scale`, and conservative full `declared_bounds`. The carton entries must reference their installed official XML paths and use their XML ClassIDs rather than guessed IDs; inspect those read-only XML files while implementing.

- [ ] **Step 4: Implement the minimal pure catalog module**

Use frozen dataclasses and explicit numeric validation:

```python
@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

@dataclass(frozen=True)
class AssetCandidate:
    key: str
    object_id: int
    class_id: int
    official_source: str
    variant: str
    intended_roles: Tuple[str, ...]
    position_enu: Vec3
    yaw_enu_rad: float
    scale: Vec3
    declared_bounds: Vec3

@dataclass(frozen=True)
class CalibrationCatalog:
    schema_version: int
    catalog_name: str
    frame: str
    units: str
    base_map: str
    owned_id_range: Tuple[int, int]
    zone_bounds: Tuple[float, float, float, float]
    placement_z: float
    station_clearance_m: float
    assets: Tuple[AssetCandidate, ...]
    sha256: str
```

Allowed roles are exactly `static_obstacle`, `dynamic_obstacle`, `color_target`, `image_target`, and `temperature_proxy`. Reject booleans as numbers and all NaN/Infinity inputs.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: `asset calibration catalog: PASS`.

- [ ] **Step 6: Commit the catalog unit**

```powershell
git add config/calibration/official_asset_candidates_v1.json scripts/calibration/__init__.py scripts/calibration/asset_catalog.py tests/asset_calibration_catalog_check.py
git commit -m "feat: define official asset calibration catalog"
```

---

### Task 2: Calibration Geometry and Deterministic Artifacts

**Files:**
- Create: `scripts/calibration/calibration_geometry.py`
- Create: `scripts/calibration/calibration_artifacts.py`
- Create: `tests/asset_calibration_geometry_check.py`
- Create: `tests/asset_calibration_artifacts_check.py`

**Interfaces:**
- Consumes: `CalibrationCatalog`, `AssetCandidate`, `Vec3`, `load_catalog`
- Produces: `enu_to_ned(point: Vec3) -> Vec3`
- Produces: `yaw_enu_to_ned(yaw_rad: float) -> float`
- Produces: `validate_station_layout(catalog: CalibrationCatalog) -> Dict[str, object]`
- Produces: `resolved_assets(catalog: CalibrationCatalog) -> List[Dict[str, object]]`
- Produces: `generate_artifacts(catalog_path: Path, output_dir: Path) -> Dict[str, object]`

- [ ] **Step 1: Write failing geometry tests**

Assert exact conversion and layout behavior:

```python
assert enu_to_ned(Vec3(3.0, 4.0, 2.0)) == Vec3(4.0, 3.0, -2.0)
assert math.isclose(yaw_enu_to_ned(0.0), math.pi / 2.0)
report = validate_station_layout(load_catalog(catalog_path))
assert report["valid"] is True
assert report["station_count"] == 10
assert report["minimum_station_clearance_m"] >= 0.75
```

Mutate temporary catalogs to make conservative bounds overlap, leave the zone,
or cross the placement plane, and assert `CalibrationGeometryError` with a
specific asset key in the message.

- [ ] **Step 2: Run geometry tests and verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_geometry_check.py --catalog-module scripts\calibration\asset_catalog.py --geometry-module scripts\calibration\calibration_geometry.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL because `calibration_geometry.py` does not exist.

- [ ] **Step 3: Implement coordinate and station geometry**

Treat `declared_bounds` as full axis-aligned dimensions for conservative station
separation. Inflate each XY half extent by `station_clearance_m / 2`, reject
strict overlap, and report the minimum edge-to-edge clearance. Require each
candidate's bottom (`position_enu.z - bounds.z / 2`) to be no lower than
`placement_z - 0.01`.

- [ ] **Step 4: Run geometry tests and verify GREEN**

Run the Step 2 command. Expected: `asset calibration geometry: PASS`.

- [ ] **Step 5: Write failing deterministic artifact tests**

Generate twice into separate temporary directories and require byte-identical:

```text
declared_profiles.json
resolved_scene.json
validation_report.json
calibration_preview.svg
artifact_manifest.json
```

Assert that each declared profile has `evidence_state: "DECLARED"`, empty
`measurements`, catalog SHA-256, official source, and no words implying live,
LiDAR, RGB, collision, or role approval. Assert the SVG contains every asset key,
zone bounds, metre grid, axes, and catalog checksum.

- [ ] **Step 6: Run artifact tests and verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_artifacts_check.py --catalog-module scripts\calibration\asset_catalog.py --geometry-module scripts\calibration\calibration_geometry.py --artifact-module scripts\calibration\calibration_artifacts.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL because `calibration_artifacts.py` does not exist.

- [ ] **Step 7: Implement deterministic artifact generation**

Serialize JSON with `ensure_ascii=False`, `indent=2`, and `sort_keys=True` plus a
trailing newline. Sort assets by object ID. Hash each artifact after writing it,
then write `artifact_manifest.json` containing catalog checksum and artifact
checksums. Use an SVG viewBox calculated from the calibration zone rather than
hard-coded V1 course coordinates.

- [ ] **Step 8: Run both focused tests and verify GREEN**

Run the Step 2 and Step 6 commands. Expected: both PASS.

- [ ] **Step 9: Commit geometry and artifacts**

```powershell
git add scripts/calibration/calibration_geometry.py scripts/calibration/calibration_artifacts.py tests/asset_calibration_geometry_check.py tests/asset_calibration_artifacts_check.py
git commit -m "feat: generate official asset calibration scene"
```

---

### Task 3: Safe Heterogeneous Official-Asset Loader

**Files:**
- Create: `scripts/calibration/ue_asset_loader.py`
- Create: `tests/asset_calibration_ue_loader_check.py`

**Interfaces:**
- Consumes: `CalibrationCatalog`, `enu_to_ned`, `yaw_enu_to_ned`
- Produces: `PlacementCommand(object_id: int, class_id: int, position_ned: Vec3, yaw_ned_rad: float, scale: Vec3)`
- Produces: `build_commands(catalog: CalibrationCatalog) -> List[PlacementCommand]`
- Produces: `place_assets(client, catalog, window_id: int, repeat: int = 3) -> Dict[str, object]`
- Produces: `remove_assets(client, catalog, window_id: int, repeat: int = 3) -> Dict[str, object]`
- Invariant: neither function calls `sendUE4Cmd`; removal enumerates catalog asset IDs, never the entire range

- [ ] **Step 1: Write the failing fake-client safety test**

Define a fake client with only `sendUE4PosScale` and `sendUE4Destroy`. Assert:

```python
commands = build_commands(catalog)
assert [c.class_id for c in commands] == [a.class_id for a in catalog.assets]
assert [c.object_id for c in commands] == [a.object_id for a in catalog.assets]
assert all(13000 <= c.object_id <= 13099 for c in commands)
```

After placement, require three identical calls per object with `MotorRPMSMean=0`
and no client method capable of changing maps. After removal, require exactly
the ten declared object IDs repeated three times; IDs not declared in the
catalog must never be destroyed.

- [ ] **Step 2: Run the loader test and verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_ue_loader_check.py --catalog-module scripts\calibration\asset_catalog.py --geometry-module scripts\calibration\calibration_geometry.py --loader-module scripts\calibration\ue_asset_loader.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL because `ue_asset_loader.py` does not exist.

- [ ] **Step 3: Implement command building and owned-ID actions**

Use the official call form:

```python
client.sendUE4PosScale(
    copterID=command.object_id,
    vehicleType=command.class_id,
    MotorRPMSMean=0,
    PosE=list(command.position_ned),
    AngEuler=[0.0, 0.0, command.yaw_ned_rad],
    Scale=list(command.scale),
    windowID=window_id,
)
```

Validate `repeat >= 1`, re-check each ID against the owned range at action time,
and return receipts with `map_change: false`, `arming_request: false`, catalog
checksum, exact acted-on IDs, and `mode: "live"`. Do not import ROS.

- [ ] **Step 4: Run loader test and verify GREEN**

Run the Step 2 command. Expected: `asset calibration UE loader: PASS`.

- [ ] **Step 5: Commit the loader**

```powershell
git add scripts/calibration/ue_asset_loader.py tests/asset_calibration_ue_loader_check.py
git commit -m "feat: add bounded official asset loader"
```

---

### Task 4: Metadata Normalization and Profile State Machine

**Files:**
- Create: `scripts/calibration/object_metadata.py`
- Create: `tests/asset_calibration_metadata_check.py`

**Interfaces:**
- Consumes: catalog candidates and raw objects shaped like RflySim `CoptReqData`
- Produces: `MetadataSample(timestamp: float, pos_vendor: Vec3, attitude_vendor: Vec3, box_origin_vendor: Vec3, half_extent_vendor: Vec3)`
- Produces: `normalize_sample(raw) -> MetadataSample`
- Produces: `analyze_samples(candidate, samples: Sequence[MetadataSample], position_tolerance_m: float = 0.02, extent_tolerance_m: float = 0.01) -> Dict[str, object]`
- Produces: `build_metadata_profile(candidate, analysis, provenance) -> Dict[str, object]`
- Produces: `record_candidate(client, candidate, sample_count: int, timeout_s: float) -> List[MetadataSample]`

- [ ] **Step 1: Write failing normalization and stability tests**

Use fake raw samples where `BoxExtent=(0.25, 0.50, 0.75)` and assert the profile
stores raw half extents and full dimensions `(0.50, 1.00, 1.50)`. Require median
values across samples, maximum position/extent deltas, sample timestamps, and
`METADATA_MEASURED` only when all samples are finite, fresh, positive in extent,
and inside tolerances.

Reject boolean/nonnumeric/NaN data, zero or negative extents, fewer than three
samples, non-monotonic timestamps, stale final samples, and inconsistent bounds.
Failed analysis must produce `REJECTED` with explicit reason codes, not raise
away the evidence.

- [ ] **Step 2: Run metadata tests and verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_metadata_check.py --catalog-module scripts\calibration\asset_catalog.py --geometry-module scripts\calibration\calibration_geometry.py --metadata-module scripts\calibration\object_metadata.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL because `object_metadata.py` does not exist.

- [ ] **Step 3: Implement pure normalization, analysis, and profiles**

Profile output must include:

```json
{
  "schema_version": 1,
  "evidence_state": "METADATA_MEASURED",
  "approved_roles": [],
  "measurements": {
    "raw_vendor": {},
    "converted_enu": {},
    "full_dimensions_m": [0.5, 1.0, 1.5],
    "sample_count": 5,
    "maximum_position_delta_m": 0.0,
    "maximum_extent_delta_m": 0.0
  },
  "provenance": {}
}
```

Never include `LIDAR_MEASURED`, `RGB_MEASURED`, or `ROLE_APPROVED` as outcomes
from this module.

- [ ] **Step 4: Add the thin official query adapter**

Use the installed API behavior documented by `GetCamObjDemo.py`:

```python
client.reqCamCoptObj(1, candidate.object_id)
client.initUE4MsgRec()
raw = client.getCamCoptObj(1, candidate.object_id)
```

Wait with a bounded monotonic deadline, consume only samples whose `hasUpdate`
is true, clear `hasUpdate` after copying, and raise `MetadataCaptureError` on
timeout. Do not query by scene object name. This plan's placed candidates are
vehicle-style ClassID instances and are queried with op type `1` and their owned
object IDs.

- [ ] **Step 5: Run metadata tests and verify GREEN**

Run the Step 2 command. Expected: `asset calibration metadata: PASS`.

- [ ] **Step 6: Commit metadata handling**

```powershell
git add scripts/calibration/object_metadata.py tests/asset_calibration_metadata_check.py
git commit -m "feat: record official asset metadata profiles"
```

---

### Task 5: Supported DryRun-First CLI and Offline Validator

**Files:**
- Create: `scripts/calibration/calibration_cli.py`
- Create: `scripts/validate_asset_calibration.ps1`
- Create: `tests/asset_calibration_cli_check.py`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: Tasks 1–4 modules
- Produces commands:
  - `generate --catalog config/calibration/official_asset_candidates_v1.json --output generated/calibration/official_assets_v1`
  - `load --catalog config/calibration/official_asset_candidates_v1.json [--execute] [--window-id N]`
  - `remove --catalog config/calibration/official_asset_candidates_v1.json [--execute] [--window-id N]`
  - `record --catalog config/calibration/official_asset_candidates_v1.json --output logs/calibration/20260813T120000Z_metadata [--execute] [--samples N] [--timeout-s S]`
- Default for `load`, `remove`, and `record`: JSON DryRun receipt and no UE client creation

- [ ] **Step 1: Write the failing CLI contract test**

Run every state-changing command without `--execute` and assert exit `0`, valid
JSON, `mode: "dry-run"`, `map_change: false`, `arming_request: false`, and exact
owned IDs. Inspect the source text and reject any of these tokens:

```text
RflyChangeMapbyName
set_mode
arming
OFFBOARD
wsl --shutdown
taskkill
pkill
```

Run `generate` twice and compare artifacts byte-for-byte. Run invalid catalog
and invalid output arguments and require nonzero exits with bounded error text.

- [ ] **Step 2: Run the CLI test and verify RED**

```powershell
D:\PX4PSP\Python38\python.exe tests\asset_calibration_cli_check.py --cli scripts\calibration\calibration_cli.py --catalog config\calibration\official_asset_candidates_v1.json
```

Expected: FAIL because the CLI does not exist.

- [ ] **Step 3: Implement the CLI dispatcher**

Create the official UE client only after parsing `--execute`. Import
`UE4CtrlAPI` from `RFLYSIM_ROOT/RflySimAPIs/RflySimSDK/ue`, defaulting
`RFLYSIM_ROOT` to `D:\PX4PSP`. `record --execute` must process candidates one at
a time, write one profile per candidate plus `metadata_run_manifest.json`, and
exit nonzero if any profile is `REJECTED` while still preserving all profiles.

For `record --execute`, verify the candidate IDs are already present by receiving
metadata; do not implicitly call `load`. This keeps placement and recording as
separate operator-visible actions.

- [ ] **Step 4: Run the CLI test and verify GREEN**

Run the Step 2 command. Expected: `asset calibration CLI: PASS`.

- [ ] **Step 5: Add the aggregate offline validator**

The PowerShell script must invoke all five focused tests through
`D:\PX4PSP\Python38\python.exe`, run CLI DryRuns, run `git diff --check`, then
print exactly:

```text
[PASS] Official asset calibration offline validation PASS
```

It must not start RflySim or WSL.

- [ ] **Step 6: Classify scripts and run the aggregate validator**

Add `scripts/validate_asset_calibration.ps1` under **Public entry** and all seven
files beneath `scripts/calibration/` under **Protected internal** in
`scripts/README.md`.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
D:\PX4PSP\Python38\python.exe tests\script_inventory_check.py --project-root .
```

Expected: both PASS.

- [ ] **Step 7: Commit the supported entry points**

```powershell
git add scripts/calibration/calibration_cli.py scripts/validate_asset_calibration.ps1 tests/asset_calibration_cli_check.py scripts/README.md
git commit -m "feat: add asset calibration command workflow"
```

---

### Task 6: Metadata Calibration Runbook and Repository Regression

**Files:**
- Create: `docs/runbooks/official-asset-metadata-calibration.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: supported CLI and validator from Task 5
- Produces: operator workflow with a hard stop before any live `--execute`

- [ ] **Step 1: Write the runbook with exact offline commands**

Document:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py generate --catalog config\calibration\official_asset_candidates_v1.json --output generated\calibration\official_assets_v1
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py load --catalog config\calibration\official_asset_candidates_v1.json
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py record --catalog config\calibration\official_asset_candidates_v1.json --output logs\calibration\20260813T120000Z_metadata
D:\PX4PSP\Python38\python.exe scripts\calibration\calibration_cli.py remove --catalog config\calibration\official_asset_candidates_v1.json
```

Explain that the last three are DryRuns without `--execute`. State that live
placement requires a healthy existing RflySim instance and explicit user review;
it does not authorize starting/stopping the live stack, arming, or flight.

- [ ] **Step 2: Document the controlled T1 live checkpoint**

Give this sequence, but mark it **not to be run during ordinary implementation**:

1. Inspect the current stack and confirm the intended RflySim window/instance.
2. Review `load` DryRun IDs, ClassIDs, positions, scales, and `map_change=false`.
3. Obtain user approval for the live placement operation if no healthy instance
   is already explicitly in scope.
4. Run `load --execute`; visually inspect that objects occupy only the calibration
   zone.
5. Run `record --execute --samples 5 --timeout-s 10`.
6. Review each profile; only `METADATA_MEASURED` or `REJECTED` are valid states.
7. Review `remove` DryRun, run `remove --execute`, and verify the ten IDs are gone.
8. Record unproven items: LiDAR, RGB, collision, dynamic motion, and role approval.

- [ ] **Step 3: Link the runbook and verify documentation**

Add it under a runbook/operations subsection of `docs/README.md`, not under
Current Truth. Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
git diff --check
```

Expected: link check PASS and no diff errors.

- [ ] **Step 4: Run scoped repository regression**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_asset_calibration.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
git status --short
```

Expected: all validators PASS. Status contains only this task's intended runbook
and index edits before commit. No live run is performed.

- [ ] **Step 5: Commit documentation**

```powershell
git add docs/runbooks/official-asset-metadata-calibration.md docs/README.md
git commit -m "docs: add official asset calibration runbook"
```

---

## Final Review Gate

- [ ] Confirm `git diff HEAD~6..HEAD --check` reports no errors.
- [ ] Confirm `git status --short` is clean or contains only pre-existing user changes.
- [ ] Confirm the original PBL-1 spec, loader, mission, lifecycle, PX4, Faster-LIO, and EGO-Swarm files were not modified.
- [ ] Confirm offline validation output is fresh and recorded in the handoff.
- [ ] Do not describe T0 results as live metadata evidence.
- [ ] Do not start or stop RflySim, WSL, PX4, or ROS without the separately required authority and safety review.
- [ ] If T1 is not run, hand off the exact DryRun receipts and list live metadata calibration as the next recommended step.

## Deferred Follow-Up Plans

1. **No-arm sensor calibration:** Mid360 cluster measurement, RGB evidence,
   official color targets, ClassID 43 ArUco/QR image generation, safe image
   deploy/restore, and simultaneous-distinct-marker capability testing.
2. **Dynamic obstacle calibration:** deterministic pendulum controller, swept
   envelope, latency, point-cloud continuity, and safe cleanup.
3. **Predicted course V2:** consume `ROLE_APPROVED` profiles, centreline-relative
   placement, static/dynamic/target randomization, standard/stress/random scene
   families, and competition-oriented automatic metrics.
