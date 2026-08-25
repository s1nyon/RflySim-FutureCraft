# Competition Course V2

Status: **DEVELOPMENT MAP — OFFLINE STRUCTURAL VALIDATION PASS; LIVE VALIDATION PENDING**

`competition_course_v2` is one reproducible RflySim development environment for the official narrow-corridor task family. It is not the final official competition map, and selecting it does not establish a shared `competition_world` TF. The protected default remains `predicted_narrow_course`.

## Requirements matrix

| Element | Source | Classification | Current implementation |
| --- | --- | --- | --- |
| At least two UAVs | `docs/reference/competition-guide-2026.pdf`, task 2.1 | OFFICIAL | Two versioned spawn poses |
| Three scored corridor sections | competition guide scoring text | OFFICIAL | Sections A/B/C |
| Corridor width no greater than 1.5 m | competition guide | OFFICIAL | 1.5/1.4/1.5 m |
| Turn radius no greater than 1 m | competition guide | OFFICIAL | Two 0.9 m bends |
| Static obstacles | competition guide | OFFICIAL | Box and pillar primitives |
| Swinging hanging obstacle | competition guide | OFFICIAL | Deterministic pendulum controller |
| Landing platform count at least UAV count, spacing at least 1.5 m | competition guide | OFFICIAL | Two pads, 1.8 m centres |
| ArUco `4x4_250` marker with random event ID | competition guide | OFFICIAL | Configurable development IDs 31/47 |
| Marker physical size | competition guide contains 0.50/0.60 m conflict | CONFIGURABLE | 0.60 m |
| Exact target asset/content | not yet fixed for this map milestone | CONFIGURABLE | Replaceable `mission_target_slot` |
| Standard QR target | target type exists in the full competition task, but no verified V2 asset requirement | CONFIGURABLE | Not implemented in this map milestone |
| Exact geometry coordinates | engineering design | PREDICTED | Versioned below |

The authoritative source is [competition_course_v2.json](../../config/maps/competition_course_v2.json). Geometry must not be duplicated in batch files or Python constants.

## Layout and parameters

```text
ENU +Y north

 landing / open area               ┌── pad 2 + ArUco 47
                                   └── pad 1 + ArUco 31
                     target slot
                         │
       section C ────────┴──────────────→ +X
              ╭ right 0.9 m
              │ section B       moving pendulum
              │    static pillar
              ╰ left 0.9 m
 start ── section A ── static box
 UAV1/UAV2
```

| Area/object | Versioned value | Classification |
| --- | --- | --- |
| Start bounds | x `[13.5,18.5]`, y `[-2.5,2.5]` | PREDICTED; accepted arena substrate |
| UAV1 / UAV2 spawn | `(16,-0.7,0)` / `(16,0.7,0)` ENU, yaw 0° | PREDICTED; accepted baseline spawn |
| Section A | `(18.5,0)` to `(23,0)`, 4.5 m, width 1.5 m | PREDICTED within OFFICIAL limits |
| Corner A | centre `(23,0.9)`, left, radius 0.9 m | PREDICTED within OFFICIAL limits |
| Section B | `(23.9,0.9)` to `(23.9,4)`, 3.1 m, width 1.4 m | PREDICTED within OFFICIAL limits |
| Corner B | centre `(24.8,4)`, right, radius 0.9 m | PREDICTED within OFFICIAL limits |
| Section C | `(24.8,4.9)` to `(29.3,4.9)`, 4.5 m, width 1.5 m | PREDICTED within OFFICIAL limits |
| Wall | 2.5 m high, 0.15 m thick, max chord error 0.02 m | PREDICTED |
| Static box | ID 15100, `(20.5,0.60,0.45)`, `0.35×0.25×0.90` m; passable side 1.225 m | PREDICTED |
| Static pillar | ID 15101, `(23.35,2.40,0.60)`, `0.20×0.30×1.20` m; passable side 1.150 m | PREDICTED |
| Pendulum | ID 15120, pivot `(27,4.9,2.4)`, length 1.2 m, ±30°, period 6 s, 20 Hz | PREDICTED/CONFIGURABLE |
| Target slot | ID 15130, `(28,5.45,1.2)`, `0.8×0.3×0.8` m | CONFIGURABLE placeholder |
| Landing bounds | x `[29.3,34.3]`, y `[2.9,6.9]` | PREDICTED; accepted arena substrate |
| Pads | centres `(32,3.9)` and `(32,5.9)`, `0.9×0.9×0.1` m | PREDICTED |
| Markers | IDs 31/47, `DICT_4X4_250`, 0.60 m marker and 0.80 m board border extent | CONFIGURABLE |

The configurable vehicle envelope is 0.45 m in diameter with 0.25 m lateral
margin on each side. Validators therefore require a 1.00 m passable opening.
At 120 Hz sampling the current pendulum profile provides a predicted 1.858 s
continuous safe window and 1.250 m maximum open-side gap; these are structural
predictions and still require live scene confirmation.

## Generate, validate, deploy, and select

Offline operations:

```powershell
scripts\generate_competition_course_v2.bat
powershell -ExecutionPolicy Bypass -File scripts\validate_competition_course_v2.ps1
scripts\deploy_competition_course_v2_terrain.bat --dry-run
scripts\load_competition_course_v2.bat --dry-run
```

The generator writes deterministic ignored output under `generated/competition_course_v2/`. It includes a spec hash, entity manifest, structural report, dimensioned preview, `evaluation_reference.json`, terrain files, and marker PNGs.

## Measurement contract

`evaluation_reference.json` is the machine-readable map side of future
competition analysis. It supplies cumulative course distance, wall/static and
landing polygons, pendulum truth and predicted safe windows, target truth, and
the clearance policy. It defines metrics for takeoff/entry time, section
completion, obstacle clearance, inter-UAV distance, collisions, OFFBOARD loss,
target error, landing error, and localization error.

| Evidence plane | Purpose | Scoring authority |
| --- | --- | --- |
| Map spec/reference | Geometry, semantics and expected motion | Reference input |
| RflySim/CopterSim ground truth | Physical pose, motion and collision truth | Primary where available |
| ROS runtime | Localization, planner and control behavior | Primary for algorithm/control state |
| Derived offline analysis | Align truth and runtime to compute errors | Derived result |
| RViz | Human debugging and visual sanity checks | **Never a score source** |

The exact RflySim ground-truth transport/API is intentionally marked
`NOT_AUDITED_IN_MAP_TASK`. This map task does not invent a ROS topic or shared
TF. A later evaluator must audit that transport and align each UAV estimate
offline using verified initial/spawn truth; it must not create a runtime
`competition_world` transform without mathematical evidence.

Live selection is explicit:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\live_stack_start.ps1 -DryRun -Course competition_course_v2
```

Omitting `-Course` continues to select `predicted_narrow_course`. Real execution still requires the standard lifecycle authorization and `-Execute`.

## Ownership and reversible deployment

- The predicted and V2 specs reserve disjoint ID ranges. Course selection derives exact IDs from both tracked specs and sends destroy commands only for those IDs; unknown scene entities are never range-swept.
- The V2 loader still uses its matching `load_receipt.json` for same-course reload/unload rollback.
- The pendulum process is registered at creation as `windows:competition_course_v2_motion` in the current stack manifest.
- Before standard stop, `scripts\load_competition_course_v2.bat --unload` requests a graceful controller stop and destroys only receipt-owned entities.
- RflySim ClassID 43 reads one fixed installed `Aruco.png`. Each marker creation uses an atomic, checksum-guarded temporary replacement and byte-exact restoration in `finally`. The installed original expected SHA-256 is `0a2983af793349abc5cccb1e30c4a491263b63b6413be703a4a3f810fe9c592a`.
- Simultaneous persistence of two different marker textures remains **PENDING LIVE VALIDATION**. Failure is a map acceptance blocker, not permission to fake the asset.

## Validation levels

| Level | Status | Meaning |
| --- | --- | --- |
| STRUCTURAL VALIDATION | PASS | Strict schema, IDs, geometry, spawn, obstacle, pendulum, ArUco, target, determinism, fake-SDK loader and dry-run contracts |
| LIVE SENSOR VALIDATION | PENDING | Both LiDARs/RGB/IMUs see a non-empty real scene; marker images are visually inspected |
| PLANNER SMOKE | PENDING | Both Faster-LIO and EGO chains remain healthy on V2 |
| FULL MISSION | NOT REQUIRED | Map correctness is separate from future mission/planner development |

The no-arm probe is installed as `competition_course_live_probe.py`. Stage 7 remains `lidar_only` by default; `--sensor-mode full` is an explicit no-arm diagnostic choice for RGB evidence. Topic activity alone is not accepted as proof that a wall, moving obstacle, or marker is visible.

## Known boundaries

- `competition_world` remains reserved/not established. The map’s ENU geometry is not a transform between `uav1_camera_init` and `uav2_camera_init`.
- The map does not implement ArUco detection, QR detection, target recognition, precision landing, coordination, or a new mission.
- V2 does not replace or modify `predicted_narrow_course_v1`; that map remains the protected regression oracle and default startup selection.
