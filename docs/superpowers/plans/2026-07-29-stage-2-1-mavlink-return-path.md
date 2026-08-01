# Stage 2.1 MAVLink Return-Path Validation Implementation Plan

> **Historical note, 2026-07-30:** The `16540/17540` FCU URL recorded below was superseded after live GUI verification showed that it is the Rfly SIL/CopterSim link. Current dual-MAVROS startup creates dedicated links: `/uav1` `udp://:14601@127.0.0.1:14600`, `/uav2` `udp://:14611@127.0.0.1:14610`. Retain this document for the original validation design; do not reuse its legacy FCU port values.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, single-UAV Stage 2.1 verifier that classifies the PX4-to-MAVROS return-path failure and blocks later live stages until `/uav1` is genuinely ready.

**Architecture:** Keep PX4/RflySim and the reference `28com_uav` project untouched. A Python verifier owns report validation, PX4-log parsing, ROS evidence collection, and conservative classification. A thin WSL runner invokes it against `/uav1`; a Windows wrapper exposes dry-run and live entry points; an offline PowerShell validator freezes the contracts without starting ROS, PX4, MAVROS, WSL GUI, RflySim3D, or CopterSim.

**Tech Stack:** Python 3 standard library; optional ROS1 Noetic `rospy`; Bash in WSL; Windows batch and PowerShell; JSON fixtures.

## Global Constraints

- Do not modify or copy `28com_sim/UAV_demo/28com_uav`, PX4 Firmware, RflySim3D, or CopterSim.
- Keep ROS logic in `future_aircraft_ws` and Windows orchestration in `scripts/`.
- Preserve `/uav1` and `/uav2`; Stage 2.1 targets only `/uav1`.
- Preserve Stage 5 `mission_events.jsonl` compatibility and all existing Stage 5/6 interfaces.
- The Stage 2.1 live path must not call `set_mode` or `cmd/arming`, publish flight setpoints, or arm a vehicle.
- WSL shell files must be LF-only.
- Offline validation must not start WSL GUI applications, RflySim3D, CopterSim, PX4, ROS, or MAVROS.
- Only a fresh `ready` report allows a future dual-UAV gate; Stage 6D and Stage 6E remain blocked otherwise.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `config/stage2_1_mavlink_link.json` | Single-UAV namespace, FCU URL, PX4 instance/log path, timeout, and report contract. |
| `future_aircraft_ws/src/multi_uav_mission/scripts/mavlink_return_path_check.py` | Pure PX4-log parsing and status classification plus optional read-only ROS sampling. |
| `tests/stage2_1_mavlink_return_path_check.py` | Standard-library regression tests for parsing and every report classification. |
| `tests/fixtures/stage2_1/px4_status_ready.log` | Stable PX4 `mavlink status` excerpt proving a bidirectional link. |
| `tests/fixtures/stage2_1/px4_status_return_blocked.log` | Stable PX4 excerpt where PX4 receives MAVROS traffic while MAVROS remains disconnected. |
| `tests/fixtures/stage2_1/expected_dry_run_report.json` | Frozen dry-run report. |
| `tests/fixtures/stage2_1/expected_runner_dry_run.txt` | Exact Windows runner dry-run output. |
| `scripts/wsl/stage2_1_single_mavlink_check.sh` | Read-only WSL live/dry-run runner for `/uav1`. |
| `scripts/run_stage2_1_mavlink_check.bat` | Windows entry point that starts the WSL runner only in live mode. |
| `scripts/validate_stage2_1.ps1` | Offline regression gate for the new config, Python tests, line endings, wrapper dry-run, and fixture. |
| `README.md` and `.agents/AGENT2READ.md` | User and agent runbooks: Stage 2.1 is the mandatory gate before Stage 6D/6E. |

### Task 1: Define Stage 2.1 Contract and Parser Tests

**Files:**
- Create: `config/stage2_1_mavlink_link.json`
- Create: `tests/stage2_1_mavlink_return_path_check.py`
- Create: `tests/fixtures/stage2_1/px4_status_ready.log`
- Create: `tests/fixtures/stage2_1/px4_status_return_blocked.log`
- Create: `tests/fixtures/stage2_1/expected_dry_run_report.json`

**Interfaces:**
- Consumes: Stage 2 port contract for `/uav1`, PX4 `out.log` text, normalized MAVROS evidence.
- Produces: fixture-backed input for `load_config(path)`, `parse_px4_mavlink_status(text)`, and `classify_report(px4, mavros)`.

- [ ] **Step 1: Add the failing regression test file**

Create `tests/stage2_1_mavlink_return_path_check.py` with these executable assertions:

```python
def test_parse_ready_status(module, fixture_dir):
    parsed = module.parse_px4_mavlink_status(
        (fixture_dir / "px4_status_ready.log").read_text(encoding="utf-8")
    )
    assert parsed == {
        "started": True,
        "mavlink_local_port": 17540,
        "mavlink_remote_port": 16540,
        "partner_ip": "127.0.0.1",
        "received_mavros_traffic": True,
    }


def test_classify_return_path_blocked(module):
    assert module.classify_report(
        {"received_mavros_traffic": True},
        {"state_topic_present": True, "connected": False, "odom_received": False,
         "set_mode_service": True, "arming_service": True},
    ) == "px4_to_mavros_return_path_blocked"
```

Include equivalent assertions for `ready`, `px4_not_started`, `mavros_not_started`, `mavros_to_px4_path_blocked`, and `inconclusive`. Load the target script with `importlib.util.spec_from_file_location` so the test uses no ROS installation.

- [ ] **Step 2: Run the new test before implementation**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\stage2_1_mavlink_return_path_check.py --script future_aircraft_ws\src\multi_uav_mission\scripts\mavlink_return_path_check.py
```

Expected: FAIL because `mavlink_return_path_check.py` does not exist.

- [ ] **Step 3: Add config and fixtures with fixed port evidence**

Create `config/stage2_1_mavlink_link.json`:

```json
{
  "stage": "2.1",
  "uav_id": "uav1",
  "namespace": "/uav1",
  "fcu_url": "udp://:16540@127.0.0.1:17540",
  "px4_instance": 1,
  "px4_out_log": "/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/instance_1/out.log",
  "timeout_s": 10,
  "state_topic": "/uav1/mavros/state",
  "odom_topic": "/uav1/mavros/local_position/odom",
  "set_mode_service": "/uav1/mavros/set_mode",
  "arming_service": "/uav1/mavros/cmd/arming"
}
```

Put a complete `mavlink status` block in each PX4 fixture. The ready fixture must include `GCS heartbeat valid`, `UDP (17540, remote port: 16540)`, `partner IP: 127.0.0.1`, and a recent `received from sysid: 1 compid: 240` line. The blocked fixture uses the same PX4 evidence; its blocked classification comes from MAVROS evidence, not from falsifying the PX4 log.

- [ ] **Step 4: Commit test contract and fixtures**

```powershell
git add config/stage2_1_mavlink_link.json tests/stage2_1_mavlink_return_path_check.py tests/fixtures/stage2_1
git commit -m "test: define stage 2.1 mavlink link contract"
```

### Task 2: Implement the Read-Only Evidence Verifier

**Files:**
- Create: `future_aircraft_ws/src/multi_uav_mission/scripts/mavlink_return_path_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`
- Test: `tests/stage2_1_mavlink_return_path_check.py`

**Interfaces:**
- Consumes: `--config Path`, `--backend dry-run|ros`, `--report Path`, optional `--px4-log Path`.
- Produces: `build_report(config, backend, px4_log_text=None) -> dict`; `parse_px4_mavlink_status(text) -> dict | None`; `classify_report(px4, mavros) -> str`.

- [ ] **Step 1: Add the minimum module that makes the parser tests meaningful**

Implement the public functions and exact classifier precedence:

```python
def classify_report(px4, mavros):
    if not px4.get("started"):
        return "px4_not_started"
    if not mavros.get("state_topic_present"):
        return "mavros_not_started"
    if px4.get("received_mavros_traffic") and (
        not mavros.get("connected") or not mavros.get("odom_received")
    ):
        return "px4_to_mavros_return_path_blocked"
    if not px4.get("received_mavros_traffic"):
        return "mavros_to_px4_path_blocked"
    if all((mavros.get("connected"), mavros.get("odom_received"),
            mavros.get("set_mode_service"), mavros.get("arming_service"))):
        return "ready"
    return "inconclusive"
```

`parse_px4_mavlink_status()` must select the final `mavlink chan: #0` block, return `started: true`, parse `UDP (<local>, remote port: <remote>)`, parse `partner IP: <address>`, and mark `received_mavros_traffic` true only when that same block has a nonzero, recent `sysid: 1 compid: 240` receive count. Return `None` for missing or malformed evidence.

- [ ] **Step 2: Implement configuration and dry-run report creation**

Validate that the config has exactly the `/uav1` fields shown in Task 1, that `px4_instance == 1`, and that `fcu_url == "udp://:16540@127.0.0.1:17540"`. Implement dry-run output with planned true evidence and write JSON using:

```python
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

The dry-run report has `backend: "dry-run"`, `status: "inconclusive"`, and `live_actions: []`; it must never claim `ready`.

- [ ] **Step 3: Implement read-only ROS sampling**

For `--backend ros`, lazily import `rospy`, initialize an anonymous node only if needed, and collect:

```python
state = rospy.wait_for_message(config["state_topic"], State, timeout=timeout_s)
odom_received = _wait_for_any_message(rospy, config["odom_topic"], timeout_s)
set_mode_service = _wait_for_service(rospy, config["set_mode_service"], timeout_s)
arming_service = _wait_for_service(rospy, config["arming_service"], timeout_s)
```

Use `state.connected` for the `connected` field. Catch every ROS wait error into an `errors` list; do not call a MAVROS service or construct a publisher.

- [ ] **Step 4: Implement PX4 evidence snapshotting**

When `--px4-log` is provided, read only the final 16 KiB of the file, invoke the existing project-local `px4-mavlink --instance 1 status` command through the WSL runner before this Python script runs, then parse the resulting appended status block. If the file is unavailable or a final block cannot be parsed, return `started: False` or `started: True, evidence_complete: False` as appropriate and classify `inconclusive`; do not guess a port from the config.

- [ ] **Step 5: Install the executable and run the test**

Add `scripts/mavlink_return_path_check.py` to the existing `catkin_install_python(PROGRAMS ...)` list in `CMakeLists.txt`. Then run:

```powershell
D:\PX4PSP\Python38\python.exe tests\stage2_1_mavlink_return_path_check.py --script future_aircraft_ws\src\multi_uav_mission\scripts\mavlink_return_path_check.py
```

Expected: PASS.

- [ ] **Step 6: Commit the verifier**

```powershell
git add future_aircraft_ws/src/multi_uav_mission/scripts/mavlink_return_path_check.py future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt tests/stage2_1_mavlink_return_path_check.py
git commit -m "feat: add stage 2.1 mavlink return verifier"
```

### Task 3: Add the WSL and Windows Runner Contracts

**Files:**
- Create: `scripts/wsl/stage2_1_single_mavlink_check.sh`
- Create: `scripts/run_stage2_1_mavlink_check.bat`
- Create: `scripts/validate_stage2_1.ps1`
- Create: `tests/fixtures/stage2_1/expected_runner_dry_run.txt`
- Test: `tests/fixtures/stage2_1/expected_dry_run_report.json`

**Interfaces:**
- Consumes: `config/stage2_1_mavlink_link.json`, `/uav1` ROS graph, PX4 instance 1 `out.log`.
- Produces: `logs/stage2_1_live/mavlink_link_report.json`; exit code 0 only for `status == "ready"` in live mode.

- [ ] **Step 1: Write the failing wrapper checks in the PowerShell validator**

Create `scripts/validate_stage2_1.ps1` with checks that both wrappers exist, both expose `--dry-run`, and the WSL file contains no CRLF byte sequence. Make it run:

```powershell
$output = & cmd /c $runner --dry-run 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Stage 2.1 dry-run failed' }
```

Expected before this task: FAIL because `scripts/run_stage2_1_mavlink_check.bat` does not exist.

- [ ] **Step 2: Implement the WSL helper**

Create an LF-only script that:

```bash
PROJECT_DIR="${FUTURE_AIRCRAFT_SIM_WSL_DIR:-/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim}"
CONFIG="$PROJECT_DIR/config/stage2_1_mavlink_link.json"
OUTPUT_DIR="$PROJECT_DIR/logs/stage2_1_live"
PX4_LOG="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/instance_1/out.log"
```

In dry-run mode, invoke the verifier with `--backend dry-run` and write `expected_dry_run_report.json` shape to a temporary output. In live mode, source `/opt/ros/noetic/setup.bash` and `$REF_28COM_UAV_WSL_DIR/devel/setup.bash`, verify that `PX4_LOG` exists, run `px4-mavlink --instance 1 status` from the instance directory with its output appended to `PX4_LOG`, then invoke the verifier with `--backend ros --px4-log "$PX4_LOG"`. The script must not start the simulator, start MAVROS, publish, call a service, or arm.

- [ ] **Step 3: Implement the Windows wrapper**

The wrapper loads `config/env_template.bat` and optional `config/env_local.bat`. Its exact dry-run text is:

```text
[DRY-RUN] Stage 2.1 single-UAV MAVLink return-path verifier
[DRY-RUN] 1. inspect PX4 instance 1 MAVLink status
[DRY-RUN] 2. sample /uav1 MAVROS state, odom, and service availability
[DRY-RUN] 3. write logs/stage2_1_live/mavlink_link_report.json
[DRY-RUN] 4. never publish setpoints or call flight-control services
```

In live mode, open one WSL process with `wsl -d %RFLYSIM_WSL_DISTRO% -e bash -lic "bash '%FUTURE_AIRCRAFT_SIM_WSL_DIR%/scripts/wsl/stage2_1_single_mavlink_check.sh'"`. Do not call `scripts/start_single_uav.bat`; the runner verifies an already-started environment so launch ownership remains explicit.

- [ ] **Step 4: Run dry-run manually**

```powershell
cmd /c scripts\run_stage2_1_mavlink_check.bat --dry-run
```

Expected: the four exact lines in Step 3 and exit code 0; no new RflySim, PX4, ROS, or MAVROS process.

- [ ] **Step 5: Commit runner contracts**

```powershell
git add scripts/wsl/stage2_1_single_mavlink_check.sh scripts/run_stage2_1_mavlink_check.bat tests/fixtures/stage2_1/expected_dry_run_report.json tests/fixtures/stage2_1/expected_runner_dry_run.txt
git commit -m "feat: add stage 2.1 single-uav runner"
```

### Task 4: Add the Offline Gate and Documentation

**Files:**
- Modify: `scripts/validate_stage2_1.ps1`
- Modify: `README.md`
- Modify: `.agents/AGENT2READ.md`
- Test: `scripts/validate_stage2_1.ps1`

**Interfaces:**
- Consumes: Stage 2.1 config, Python regression test, dry-run runner, and dry-run fixture.
- Produces: `powershell -ExecutionPolicy Bypass -File scripts/validate_stage2_1.ps1`, exit code 0 only when the offline Stage 2.1 contract is intact.

- [ ] **Step 1: Implement the offline validation script**

Follow the existing `validate_stage6d.ps1` structure. Require every file from the File Structure table. Verify JSON fields exactly, including `/uav1`, `px4_instance: 1`, and `udp://:16540@127.0.0.1:17540`. Verify the WSL file bytes contain no `13,10` pair. Run the Python test and compare the wrapper dry-run output to a new text fixture `tests/fixtures/stage2_1/expected_runner_dry_run.txt` using `.Trim()` on both values.

The validator must reject any WSL helper containing `cmd/arming`, `set_mode`, `setpoint`, `rospy.Publisher`, or `start_two_uav.bat` outside its descriptive dry-run text. It then invokes `scripts/validate_stage2.ps1 -Quiet` as a regression.

- [ ] **Step 2: Run the validator before documentation edits**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2_1.ps1
```

Expected: PASS. The command must create no GUI, PX4, ROS, MAVROS, or WSL live process.

- [ ] **Step 3: Update the runbooks**

In `README.md`, replace the current immediate Stage 6D instruction with this order:

1. Start the chosen single-UAV simulation path.
2. Run `scripts\run_stage2_1_mavlink_check.bat` and inspect `logs/stage2_1_live/mavlink_link_report.json`.
3. Continue only if `status` is `ready`; otherwise fix the classified boundary.
4. After the dual-UAV extension passes, run Stage 6D no-arm smoke.

In `.agents/AGENT2READ.md`, add the same hard gate and state that `px4_to_mavros_return_path_blocked` means PX4 received MAVROS traffic while MAVROS did not receive a usable PX4 return stream. Do not say that Stage 6D or Stage 6E has passed.

- [ ] **Step 4: Run the final offline regression suite**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2_1.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
git diff --check
```

Expected: all validators PASS and `git diff --check` produces no output.

- [ ] **Step 5: Commit the gate and docs**

```powershell
git add scripts/validate_stage2_1.ps1 README.md .agents/AGENT2READ.md
git commit -m "docs: gate live smoke on stage 2.1"
```

## Self-Review

- Spec coverage: Tasks 1-2 implement the report, parsed PX4/MAVROS evidence, all six classifications, no-flight safety, and catkin installation. Task 3 creates the dry-run/live runners and report location. Task 4 adds the offline gate, existing-stage regression, and runbooks.
- Placeholder scan: No task depends on unspecified APIs; all functions, file paths, ports, fixture names, expected commands, and exit criteria are named explicitly.
- Type consistency: `parse_px4_mavlink_status()` returns PX4 evidence, `classify_report()` returns one of the documented status strings, and `build_report()` writes the JSON consumed by the WSL runner. The single config uses `/uav1` and `16540/17540` consistently.
