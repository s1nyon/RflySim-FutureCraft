# Stage 2 Safe Dual-UAV Spawn Positions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start the two ChallengeMap vehicles at visibly separate candidate positions inside the accepted ChallengeMap area.

**Architecture:** `config/env_template.bat` supplies the coordinate lists to the generated project-local SITL wrapper.  `scripts/validate_stage2.ps1` freezes those generated values so a future edit cannot silently restore the overlapping pair.

**Tech Stack:** Windows batch configuration, PowerShell validator, RflySim/CopterSim/PX4 SITL.

## Global Constraints

- Do not modify `28com_sim`, Firmware, CopterSim, or RflySim3D.
- Preserve `/uav1`, `/uav2`, all MAVLink ports, and `ChallengeMap`.
- Keep both yaw values at `0` degrees.
- Do not arm, set mode, or publish flight-control setpoints during visual spawn validation.

---

### Task 1: Freeze the separated spawn contract

**Files:**
- Modify: `scripts/validate_stage2.ps1:125-128`
- Modify: `config/env_template.bat:21-24`
- Test: `scripts/validate_stage2.ps1`

**Interfaces:**
- Consumes: `STAGE2_POS_X_STR`, `STAGE2_POS_Y_STR`, and `STAGE2_YAW_STR`.
- Produces: generated SITL wrapper values `0.5,1.5`, `1.5,1.5`, and `0,0`.

- [ ] **Step 1: Update the validator expectation first**

Replace the generated-wrapper marker array with:

```powershell
@('SET PosXStr=0.5,1.5', 'SET PosYStr=1.5,1.5', 'SET YawStr=0,0')
```

- [ ] **Step 2: Run the validator and observe its failure**

Run: `powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1`

Expected: FAIL because `env_template.bat` still generates the previous overlapping candidate points.

- [ ] **Step 3: Set the separated coordinates**

Set these exact lines in `config/env_template.bat`:

```bat
set STAGE2_POS_X_STR=0.5,1.5
set STAGE2_POS_Y_STR=1.5,1.5
set STAGE2_YAW_STR=0,0
```

- [ ] **Step 4: Verify the offline contract and dry-run**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_stage2.ps1
cmd /c scripts\start_rflysim_sitl_two.bat --dry-run
```

Expected: validator PASS and dry-run prints the two separated coordinate lists.

- [ ] **Step 5: Commit**

```powershell
git add config/env_template.bat scripts/validate_stage2.ps1
git commit -m "fix: separate dual-UAV spawn positions"
```

### Task 2: Confirm the candidate points in ChallengeMap

**Files:**
- Runtime output only: RflySim/CopterSim/PX4 windows

**Interfaces:**
- Consumes: the Task 1 coordinate lists.
- Produces: a top-down visual acceptance that each vehicle is inside the map and clear of walls and the other vehicle.

- [ ] **Step 1: Stop the current dual-UAV simulation stack**

Use the project shutdown entry point or close only the simulation/MAVROS windows; do not alter project files.

- [ ] **Step 2: Start the updated dual-UAV stack**

Run: `cmd /c scripts\start_two_uav.bat`

- [ ] **Step 3: Inspect the top-down ChallengeMap view**

Accept only if both models are visibly separate, inside the room boundary, and have a clear wall margin.  Do not run Stage 6E or any arm/mode/setpoint command.

- [ ] **Step 4: Commit no runtime output**

Keep runtime logs out of this configuration-only commit unless the repository already tracks a specific evidence file.
