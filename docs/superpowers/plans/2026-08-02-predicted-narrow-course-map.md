# Predicted Narrow-Course Map V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Python-generated RflySim course containing a two-UAV takeoff area, a regulation-sized S-shaped narrow passage, and a two-platform landing area.

**Architecture:** A versioned JSON file is the single source of truth. Pure-Python geometry code validates it and derives wall boxes, platform boxes, planning points, a preview, and flat CopterSim terrain; thin adapters then publish the points to ROS or send the boxes to RflySim3D through `UE4CtrlAPI`. A dedicated launcher selects `VisionRingBlank`, applies ENU-to-NED spawn conversion, and loads only course-owned entity IDs.

**Tech Stack:** Python 3.8 standard library, ROS1 Noetic `rospy`/`sensor_msgs`, RflySim `UE4CtrlAPI`, PowerShell validators, Windows batch launchers, JSON, SVG, 16-bit grayscale PNG.

## Global Constraints

- Keep all editable implementation inside `future_aircraft_sim`; do not modify or copy `28com_sim`, RflySim3D, CopterSim, Firmware, or general RflySim examples.
- Preserve `/uav1`, `/uav2`, Stage 5 mission events, Stage 7 sensor isolation, and all simulation-only arming gates.
- Course coordinates are ENU metres; convert positions to RflySim/PX4 NED as `[north=y, east=x, down=-z]` and yaw as `pi/2-yaw_enu`.
- Use `VisionRingBlank` as the UE and CopterSim base-map name; the course itself is a dynamic object layer, not a `.umap`.
- Passage clear widths are 1.5 m, 1.4 m, and 1.5 m; both centreline turn radii are 0.9 m; wall height is 2.5 m and wall thickness is 0.15 m.
- Takeoff poses are `(0.0,-0.7,0.0)` and `(0.0,0.7,0.0)` ENU. Landing-platform centres are `(16.0,3.9)` and `(16.0,5.9)` ENU.
- Runtime loading may destroy only the deterministic course-owned ID range `12000..12999`.
- Generation and offline validation never start RflySim, publish flight setpoints, request OFFBOARD, or arm a vehicle.
- No new third-party Python dependency is allowed; PNG and SVG generation use the Python standard library.

---

## File Structure

- Create `config/maps/predicted_narrow_course_v1.json`: authoritative dimensions, centreline, assets, IDs, poses, and terrain bounds.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_geometry.py`: pure parsing, geometry, validation, checksums, and coordinate conversion.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_artifacts.py`: point sampling, SVG/report generation, and dependency-free 16-bit PNG/TXT generation.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_ue_loader.py`: dry-run command plan plus live `UE4CtrlAPI` adapter.
- Create `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_cloud_server.py`: latched ROS global-cloud publisher using the shared geometry.
- Create `future_aircraft_ws/src/multi_uav_mission/launch/predicted_narrow_course.launch`: ROS global-cloud launch entrypoint.
- Create `scripts/generate_predicted_narrow_course.bat`: Windows artifact-generation wrapper.
- Create `scripts/load_predicted_narrow_course.bat`: Windows RflySim scene-loader wrapper.
- Create `scripts/start_predicted_course_two_uav.bat`: map-specific two-UAV orchestration and dry-run entrypoint.
- Create `scripts/validate_stage8.ps1`: deterministic offline acceptance runner.
- Create `tests/stage8_course_geometry_check.py`: geometry and competition-constraint contract.
- Create `tests/stage8_course_artifacts_check.py`: SVG, report, point sampling, PNG, and TXT contract.
- Create `tests/stage8_course_ue_loader_check.py`: RflySim command planning, coordinate conversion, ID ownership, and fake-client contract.
- Create `tests/stage8_course_launch_check.py`: batch/launch/CMake integration contract.
- Modify `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`: install the three new executable Python adapters.
- Modify `config/env_template.bat`: add guarded course defaults without changing the ordinary Stage 2 defaults.
- Modify `scripts/start_rflysim_sitl_two.bat`: replace `UE4_MAP` in the generated temporary copy from an environment override.
- Modify `.gitignore`: ignore reproducible `generated/` outputs.
- Modify `README.md` and `.agents/AGENT2READ.md`: document Stage 8 generation, loading, safety boundary, and live order.

### Task 1: Course Contract and Pure Geometry

**Files:**
- Create: `config/maps/predicted_narrow_course_v1.json`
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_geometry.py`
- Create: `tests/stage8_course_geometry_check.py`

**Interfaces:**
- Produces: `Vec3`, `Pose`, `BoxObject`, `CourseModel`, and `CourseValidationError` dataclasses/classes.
- Produces: `load_course(path: Path) -> CourseModel`.
- Produces: `enu_to_ned(position: Vec3) -> Vec3` and `yaw_enu_to_ned(yaw_rad: float) -> float`.
- Produces: `course_report(model: CourseModel) -> dict` with `spec_sha256`, `centreline_length_m`, `minimum_clear_width_m`, `maximum_turn_radius_m`, `takeoff_separation_m`, `platform_spacing_m`, and `object_count`.

- [ ] **Step 1: Write the failing geometry contract**

Create a standalone assertion-based test that imports the module by file path, loads the committed JSON, and checks the approved values:

```python
model = module.load_course(args.spec)
report = module.course_report(model)
assert math.isclose(report["centreline_length_m"], 14.927433, abs_tol=1e-6)
assert report["minimum_clear_width_m"] == 1.4
assert report["maximum_turn_radius_m"] == 0.9
assert report["takeoff_separation_m"] == 1.4
assert report["platform_spacing_m"] == 2.0
assert module.enu_to_ned(module.Vec3(3.0, 4.0, 2.0)) == module.Vec3(4.0, 3.0, -2.0)
assert math.isclose(module.yaw_enu_to_ned(0.0), math.pi / 2.0)
```

Also mutate in-memory copies to assert rejection of width `1.51`, turn radius `1.01`, platform spacing `1.5`, duplicate IDs, non-finite coordinates, walls intersecting a 0.45 m takeoff envelope, and schema version `2`.

- [ ] **Step 2: Run the contract and confirm the expected failure**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_geometry_check.py --module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --spec config\maps\predicted_narrow_course_v1.json
```

Expected: non-zero exit because the module and specification do not exist.

- [ ] **Step 3: Add the exact V1 JSON specification**

Encode:

```json
{
  "schema_version": 1,
  "course_name": "predicted_narrow_course_v1",
  "base_map": "VisionRingBlank",
  "frame": "ENU",
  "units": "m",
  "owned_id_range": [12000, 12999],
  "wall": {"height": 2.5, "thickness": 0.15, "max_chord_error": 0.02},
  "vehicle_envelope": {"horizontal_diameter": 0.45},
  "takeoff_zone": {"bounds": [-2.5, 2.5, -2.5, 2.5]},
  "zone_surfaces": [
    {"name": "takeoff_surface", "id": 12790, "center": [0.0, 0.0, -0.01], "size": [5.0, 5.0, 0.02]},
    {"name": "landing_surface", "id": 12791, "center": [15.8, 4.9, -0.01], "size": [5.0, 4.0, 0.02]}
  ],
  "takeoff_poses": [
    {"name": "uav1", "position": [0.0, -0.7, 0.0], "yaw": 0.0},
    {"name": "uav2", "position": [0.0, 0.7, 0.0], "yaw": 0.0}
  ],
  "centreline": [
    {"kind": "line", "start": [2.5, 0.0], "end": [7.0, 0.0], "width": 1.5},
    {"kind": "arc", "start": [7.0, 0.0], "end": [7.9, 0.9], "center": [7.0, 0.9], "radius": 0.9, "turn": "left", "width": 1.5},
    {"kind": "line", "start": [7.9, 0.9], "end": [7.9, 4.0], "width": 1.4},
    {"kind": "arc", "start": [7.9, 4.0], "end": [8.8, 4.9], "center": [8.8, 4.0], "radius": 0.9, "turn": "right", "width": 1.4},
    {"kind": "line", "start": [8.8, 4.9], "end": [13.3, 4.9], "width": 1.5}
  ],
  "landing_zone": {"bounds": [13.3, 18.3, 2.9, 6.9]},
  "landing_platforms": [
    {"name": "platform1", "id": 12800, "center": [16.0, 3.9, 0.05], "size": [0.8, 0.8, 0.1]},
    {"name": "platform2", "id": 12801, "center": [16.0, 5.9, 0.05], "size": [0.8, 0.8, 0.1]}
  ],
  "asset": {"vehicle_type": 1000813, "native_size": [1.0, 1.0, 1.0]},
  "terrain": {"bounds": [-25.0, 25.0, -25.0, 25.0], "pixels": [513, 513], "height_raw": 32768}
}
```

- [ ] **Step 4: Implement parsing, validation, and wall tessellation**

Use immutable dataclasses. Convert each line to two offset wall boxes. Tessellate each arc until `radius * (1-cos(delta/2)) <= 0.02`, create a pair of chord-aligned boxes per interval, place box centres at `z=1.25`, and assign deterministic wall IDs starting at `12000`. Preserve zone-surface IDs `12790..12791` and reject any computed wall ID that reaches that reserved range; preserve platform IDs beginning at `12800`.

Compute the SHA-256 from the exact JSON bytes. Validate adjacency between consecutive centreline elements to `1e-6`, exact arc endpoint radii, guide limits, zone containment, platform spacing, object-ID uniqueness, and takeoff-envelope clearance.

- [ ] **Step 5: Run the geometry contract**

Run the command from Step 2.

Expected: `stage8 course geometry: PASS`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add config/maps/predicted_narrow_course_v1.json future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_geometry.py tests/stage8_course_geometry_check.py
git commit -m "feat: define predicted narrow course geometry"
```

### Task 2: Deterministic Preview, Planning Points, and Flat Terrain

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_artifacts.py`
- Create: `tests/stage8_course_artifacts_check.py`
- Create: `scripts/generate_predicted_narrow_course.bat`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `load_course()` and `course_report()` from Task 1.
- Produces: `sample_surface_points(model: CourseModel, spacing_m: float) -> list[tuple[float, float, float]]`.
- Produces: `write_flat_png16(path: Path, width: int, height: int, raw_value: int) -> None`.
- Produces: `generate_artifacts(spec_path: Path, output_dir: Path) -> dict` returning an artifact manifest with SHA-256 values.

- [ ] **Step 1: Write the failing artifact contract**

Use a temporary directory and assert:

```python
manifest = module.generate_artifacts(args.spec, output_dir)
assert sorted(path.name for path in output_dir.iterdir()) == [
    "VisionRingBlank.png", "VisionRingBlank.txt", "course_preview.svg",
    "planning_points.json", "validation_report.json"
]
assert manifest["spec_sha256"] == json.loads((output_dir / "validation_report.json").read_text())["spec_sha256"]
png = (output_dir / "VisionRingBlank.png").read_bytes()
assert png[:8] == b"\x89PNG\r\n\x1a\n"
assert png[24] == 16 and png[25] == 0
assert "32768" not in (output_dir / "VisionRingBlank.txt").read_text()
assert len(json.loads((output_dir / "planning_points.json").read_text())["points"]) > 1000
```

Parse PNG chunks with `struct` and `zlib`; assert all 513×513 decoded samples equal big-endian `32768`. Assert the TXT is `2500,2500,0,-2500,-2500,0,0,0,0` and the SVG contains takeoff IDs, platform IDs, dimensions, axes, and `spec_sha256`.

- [ ] **Step 2: Run the artifact contract and confirm failure**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_artifacts_check.py --geometry-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --artifact-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_artifacts.py --spec config\maps\predicted_narrow_course_v1.json
```

Expected: non-zero exit because `narrow_course_artifacts.py` does not exist.

- [ ] **Step 3: Implement artifact generation**

Sample all six faces of every wall and the exposed top/sides of each landing platform at no more than 0.10 m spacing; exclude the two zone surfaces from the planning cloud. Deduplicate points by integer 1 mm keys, sort by `(x,y,z)`, and write JSON using stable separators and sorted keys. Draw an SVG with a fixed `viewBox`, metre grid, zone surfaces, wall footprints, centreline, pose arrows, dimensions, and checksum.

Write PNG chunks `IHDR`, `IDAT`, and `IEND` with CRC32 from `binascii.crc32`; encode each scanline as filter byte zero followed by big-endian unsigned 16-bit samples. Write the nine-field terrain calibration in UE centimetres for the ±25 m bounds and zero altitude.

- [ ] **Step 4: Add the Windows generator wrapper and ignore generated outputs**

The batch wrapper resolves the project directory, calls `%PYTHON_EXE% narrow_course_artifacts.py --spec ... --output generated\predicted_narrow_course_v1`, supports `--dry-run`, and propagates the Python exit code. Add `generated/` to `.gitignore`; these artifacts are reproducible and are not hand-edited.

- [ ] **Step 5: Run artifact tests and generate a local usable artifact set**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_artifacts_check.py --geometry-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --artifact-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_artifacts.py --spec config\maps\predicted_narrow_course_v1.json
cmd /c scripts\generate_predicted_narrow_course.bat
```

Expected: test prints `stage8 course artifacts: PASS`; generator writes the five declared files and reports the spec checksum.

- [ ] **Step 6: Commit Task 2**

```powershell
git add .gitignore scripts/generate_predicted_narrow_course.bat future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_artifacts.py tests/stage8_course_artifacts_check.py
git commit -m "feat: generate narrow course artifacts"
```

### Task 3: Safe RflySim3D Dynamic Scene Loader

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_ue_loader.py`
- Create: `tests/stage8_course_ue_loader_check.py`
- Create: `scripts/load_predicted_narrow_course.bat`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`

**Interfaces:**
- Consumes: `CourseModel`, `BoxObject`, `load_course()`, `enu_to_ned()`, and `yaw_enu_to_ned()`.
- Produces: `UECommand(copter_id: int, vehicle_type: int, position_ned: Vec3, yaw_ned: float, scale: Vec3)`.
- Produces: `build_ue_commands(model: CourseModel) -> list[UECommand]`.
- Produces: `load_scene(client, model: CourseModel, clear_first: bool, window_id: int) -> dict` where `client` implements `sendUE4Cmd`, `sendUE4Destroy`, and `sendUE4PosScale`.

- [ ] **Step 1: Write the failing loader contract with a fake client**

Assert command count and deterministic IDs, then use:

```python
client = FakeUEClient()
result = module.load_scene(client, model, clear_first=True, window_id=0)
assert client.map_commands == ["RflyChangeMapbyName VisionRingBlank"]
assert client.destroyed == list(range(12000, 13000))
assert [call[0] for call in client.created] == [obj.copter_id for obj in module.build_ue_commands(model)]
assert result["spec_sha256"] == model.spec_sha256
```

Assert each creation uses `vehicle_type=1000813`, scale equals desired box size divided component-wise by `[1,1,1]`, Z is negative after ENU-to-NED conversion, and `--dry-run` emits JSON without importing `UE4CtrlAPI`.

- [ ] **Step 2: Run the loader contract and confirm failure**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_ue_loader_check.py --geometry-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --loader-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_ue_loader.py --spec config\maps\predicted_narrow_course_v1.json
```

Expected: non-zero exit because the loader does not exist.

- [ ] **Step 3: Implement dry-run planning and live adapter**

Build commands without importing RflySim code. In live mode, prepend `%RFLYSIM_ROOT%\RflySimAPIs\RflySimSDK\ue` to `sys.path`, import `UE4CtrlAPI`, switch the base map, wait the configured three seconds, optionally destroy exactly IDs `12000..12999`, and call:

```python
client.sendUE4PosScale(
    copterID=command.copter_id,
    vehicleType=command.vehicle_type,
    MotorRPMSMean=0,
    PosE=list(command.position_ned),
    AngEuler=[0.0, 0.0, command.yaw_ned],
    Scale=list(command.scale),
    windowID=window_id,
)
```

Repeat each creation packet three times with a 20 ms interval to tolerate UDP loss. Return and print a JSON receipt containing spec checksum, map name, object count, ID range, window, and mode.

- [ ] **Step 4: Add wrapper and Catkin installation**

`load_predicted_narrow_course.bat` loads project environment, requires the generated validation report to match the current spec checksum, accepts `--dry-run`, `--window-id N`, and `--no-clear`, and invokes the loader. Add `narrow_course_ue_loader.py`, `narrow_course_artifacts.py`, and `narrow_course_geometry.py` to `catkin_install_python`.

- [ ] **Step 5: Run loader and existing import contracts**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_ue_loader_check.py --geometry-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --loader-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_ue_loader.py --spec config\maps\predicted_narrow_course_v1.json
cmd /c scripts\load_predicted_narrow_course.bat --dry-run
```

Expected: loader test passes and dry-run prints map `VisionRingBlank`, owned IDs only, and no network side effects.

- [ ] **Step 6: Commit Task 3**

```powershell
git add scripts/load_predicted_narrow_course.bat future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_ue_loader.py tests/stage8_course_ue_loader_check.py
git commit -m "feat: load narrow course into RflySim"
```

### Task 4: ROS Planning-Cloud Publisher

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_cloud_server.py`
- Create: `future_aircraft_ws/src/multi_uav_mission/launch/predicted_narrow_course.launch`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`
- Extend: `tests/stage8_course_artifacts_check.py`

**Interfaces:**
- Consumes: `sample_surface_points()` from Task 2.
- Produces: pure `pack_xyz32(points: Sequence[tuple[float,float,float]]) -> bytes` using little-endian floats.
- Produces live ROS topic `/predicted_narrow_course/global_cloud` with frame `world`, fields `x/y/z`, point step 12, latched publisher, and a 1 Hz refreshed timestamp.

- [ ] **Step 1: Extend the failing artifact contract**

Load the cloud module without ROS and assert:

```python
payload = cloud_module.pack_xyz32([(1.0, 2.0, 3.0), (-1.0, 0.5, 4.0)])
assert len(payload) == 24
assert struct.unpack("<ffffff", payload) == (1.0, 2.0, 3.0, -1.0, 0.5, 4.0)
```

Also assert that the launch file remaps no `/uav1` or `/uav2` sensor topic and passes only `spec`, `topic`, `frame_id`, and `spacing_m`.

- [ ] **Step 2: Run and confirm failure**

Run the Task 2 artifact test with an added `--cloud-module` argument.

Expected: non-zero exit because the cloud module and launch file do not exist.

- [ ] **Step 3: Implement the ROS adapter**

Keep `struct` packing and geometry import usable without ROS. Import `rospy`, `PointCloud2`, and `PointField` only inside `main()`. Publish a latched cloud with exact float32 field offsets 0, 4, and 8; reject empty geometry and non-positive spacing before `rospy.init_node`.

- [ ] **Step 4: Add launch and installation wiring**

Create a launch file with defaults pointing through `$(find multi_uav_mission)` to the committed course spec. Add `narrow_course_cloud_server.py` to `catkin_install_python` without duplicate entries.

- [ ] **Step 5: Run offline and WSL import checks**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_artifacts_check.py --geometry-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_geometry.py --artifact-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_artifacts.py --cloud-module future_aircraft_ws\src\multi_uav_mission\scripts\narrow_course_cloud_server.py --launch future_aircraft_ws\src\multi_uav_mission\launch\predicted_narrow_course.launch --spec config\maps\predicted_narrow_course_v1.json
wsl -d RflySim-20.04 -e bash -lc "source /opt/ros/noetic/setup.bash && python3 -m py_compile /mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_cloud_server.py"
```

Expected: artifact/cloud contract passes and WSL compilation exits zero.

- [ ] **Step 6: Commit Task 4**

```powershell
git add future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt future_aircraft_ws/src/multi_uav_mission/launch/predicted_narrow_course.launch future_aircraft_ws/src/multi_uav_mission/scripts/narrow_course_cloud_server.py tests/stage8_course_artifacts_check.py
git commit -m "feat: publish narrow course planning cloud"
```

### Task 5: Course-Specific Dual-UAV Launch Integration

**Files:**
- Create: `scripts/start_predicted_course_two_uav.bat`
- Create: `tests/stage8_course_launch_check.py`
- Modify: `config/env_template.bat`
- Modify: `scripts/start_rflysim_sitl_two.bat`

**Interfaces:**
- Consumes: `PREDICTED_COURSE_BASE_MAP`, `PREDICTED_COURSE_POS_X_STR`, `PREDICTED_COURSE_POS_Y_STR`, and `PREDICTED_COURSE_YAW_STR`.
- Produces: a dry-run contract showing generation, `VisionRingBlank`, NED spawn lists `-0.7,0.7` and `0,0`, ordinary dual launch, scene loading, and no arm-capable runner.

- [ ] **Step 1: Write the failing launch contract**

Run each new/existing batch file with `--dry-run` via `subprocess.run`. Assert the course wrapper output contains:

```text
base map: VisionRingBlank
NED PosX: -0.7,0.7
NED PosY: 0,0
generate_predicted_narrow_course.bat
start_two_uav.bat
load_predicted_narrow_course.bat
```

Read the generated SITL wrapper in `--generate-only` mode and assert it contains `SET UE4_MAP=VisionRingBlank` while the reference `28com_sim/28com_SITL/UAVSITL.bat` still contains `SET UE4_MAP=ChallengeMap`.

- [ ] **Step 2: Run and confirm failure**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_launch_check.py --project-root .
```

Expected: non-zero exit because the course launcher and map override do not exist.

- [ ] **Step 3: Add guarded environment defaults and generated-wrapper substitutions**

In `env_template.bat`, use `if not defined` for the existing Stage 2 position/yaw variables, then add exact course defaults:

```bat
if not defined PREDICTED_COURSE_BASE_MAP set PREDICTED_COURSE_BASE_MAP=VisionRingBlank
if not defined PREDICTED_COURSE_POS_X_STR set PREDICTED_COURSE_POS_X_STR=-0.7,0.7
if not defined PREDICTED_COURSE_POS_Y_STR set PREDICTED_COURSE_POS_Y_STR=0,0
if not defined PREDICTED_COURSE_YAW_STR set PREDICTED_COURSE_YAW_STR=90,90
```

Extend the PowerShell transformation in `start_rflysim_sitl_two.bat` to replace the exact reference line `SET UE4_MAP=ChallengeMap` with `SET UE4_MAP=` plus `RFLYSIM_UE4_MAP`, defaulting to `ChallengeMap`. Continue modifying only `%TEMP%\future_aircraft_stage2_uavsitl.bat`.

- [ ] **Step 4: Implement the course orchestration wrapper**

The wrapper sets `RFLYSIM_UE4_MAP`, `STAGE2_POS_X_STR`, `STAGE2_POS_Y_STR`, and `STAGE2_YAW_STR` from the course values, generates artifacts, starts the ordinary dual-UAV path, waits until that launcher returns from its existing boot wait, then loads the dynamic scene. `--dry-run` calls only downstream dry-runs and prints the exact sequence; it never starts a GUI, ROS, PX4, CopterSim, or RflySim.

- [ ] **Step 5: Run launch and existing Stage 2 dry-run contracts**

```powershell
D:\PX4PSP\Python38\python.exe tests\stage8_course_launch_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
```

Expected: Stage 8 launch contract and existing Stage 2 validator pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add config/env_template.bat scripts/start_rflysim_sitl_two.bat scripts/start_predicted_course_two_uav.bat tests/stage8_course_launch_check.py
git commit -m "feat: add predicted course dual launch"
```

### Task 6: Stage 8 Validator, Documentation, and No-Arm Acceptance Runbook

**Files:**
- Create: `scripts/validate_stage8.ps1`
- Modify: `README.md`
- Modify: `.agents/AGENT2READ.md`
- Extend: `tests/stage8_course_launch_check.py`

**Interfaces:**
- Consumes: all Task 1-5 contracts and existing Stage 7 validator.
- Produces: one offline command that regenerates artifacts, verifies deterministic checksums, and reports `Stage 8 predicted narrow course offline validation PASS`.

- [ ] **Step 1: Write the validator as a failing aggregation gate**

First extend `stage8_course_launch_check.py` to require the literal Stage 8 commands and the no-arm boundary in both `README.md` and `.agents/AGENT2READ.md`. Implement strict `$ErrorActionPreference = 'Stop'` orchestration of the four Stage 8 Python contracts, both batch dry-runs, artifact regeneration into a temporary directory, byte comparison of two independently generated output sets, `git diff --check`, and `scripts\validate_stage7.ps1`. Preserve and return the first non-zero exit code.

Before Task 6 documentation changes, run it once and record the expected failure caused by missing README/handbook Stage 8 markers checked by `stage8_course_launch_check.py`.

- [ ] **Step 2: Document exact operator workflow**

Add these commands and boundaries to both documents:

```bat
scripts\validate_stage8.ps1
scripts\generate_predicted_narrow_course.bat
scripts\start_predicted_course_two_uav.bat --dry-run
scripts\start_predicted_course_two_uav.bat
```

Document that the fourth command starts GUI simulation but does not itself arm; after startup the operator must run Stage 7 no-arm sensor readiness and topic probe before any separately authorized simulation-only flight. State that dynamic wall collision is validated by LiDAR/geometric clearance, not CopterSim height terrain.

- [ ] **Step 3: Run the full offline acceptance suite**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected final line: `Stage 8 predicted narrow course offline validation PASS`.

- [ ] **Step 4: Inspect generated preview and validation report**

Open `generated/predicted_narrow_course_v1/course_preview.svg` as text and verify it contains the two takeoff poses, S-course wall paths, two platforms, dimensions, and checksum. Read `validation_report.json` and confirm centreline `14.927433`, minimum width `1.4`, maximum turn radius `0.9`, takeoff separation `1.4`, and platform spacing `2.0`.

- [ ] **Step 5: Commit Task 6**

```powershell
git add scripts/validate_stage8.ps1 README.md .agents/AGENT2READ.md
git commit -m "docs: add stage8 course runbook"
```

- [ ] **Step 6: Perform the optional live no-arm map acceptance**

Only when a desktop RflySim session is available, run:

```bat
scripts\start_predicted_course_two_uav.bat
scripts\run_live_fastlio_dual.bat
scripts\run_stage7_topic_probe.bat
```

Visually confirm all course objects, then verify both isolated LiDAR streams contain returns from a wall at a geometrically expected range. Record screenshots, loader receipt, current `sensor_readiness.json`, and `topic_probe_report.json`. Do not run `run_live_slam_ego_swarm_flight.bat` during map acceptance.
