# Future Aircraft Sim Project Structure Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `future_aircraft_sim` into a reproducible, clearly owned competition-development repository while preserving the live-validated Python and lifecycle baselines.

**Architecture:** Keep the validated `multi_uav_mission` Python package and live script paths stable, move new user C++ into `future_aircraft_mission`, pin the team's EGO fork as a separate `third_party` Catkin overlay, and add a thin root `sim.ps1` that delegates to protected lifecycle scripts. Perform destructive runtime cleanup only after dependency, build, contract, and evidence checks succeed.

**Tech Stack:** Windows PowerShell 5.1, batch, WSL Ubuntu 20.04, Bash, ROS1 Noetic, Catkin, C++17, Python 3 contract tests, Git submodules, RflySim/PX4/MAVROS/Faster-LIO/EGO-Swarm.

## Global Constraints

- Do not modify the behavior of existing Python files under `future_aircraft_ws/src/multi_uav_mission/scripts/`.
- Do not delete or relocate a script that participates in the current live chain.
- Preserve both `.vscode` configurations and commit them.
- Preserve all uncommitted C++ work before restoring `multi_uav_mission/CMakeLists.txt` or `package.xml`.
- Preserve the current 21-file EGO diff before moving, recloning, or deleting `external/ego-planner-swarm`.
- The final EGO source is a fetchable team-fork submodule at `third_party/ego-planner-swarm` pinned to an exact commit.
- Never push either repository without explicit user authorization.
- Keep lifecycle fail-closed semantics: no name-based killing, `wsl --shutdown`, implicit forced cleanup, automatic force retry, or implicit arming.
- `sim.ps1 start`, `stop`, and `clean-logs` default to DryRun and require `-Execute` for mutations.
- Do not move the runtime paths `logs/` or `generated/`.
- Do not run a full flight automatically. A no-arm live check requires a separate execution decision after offline validation.
- Use `apply_patch` for hand-authored file changes. Generated patch/evidence files may be produced by their dedicated scripts.
- Stage and commit only files named by the current task; preserve unrelated user changes.

---

## File and Responsibility Map

### New files

- `third_party/README.md`: dependency ownership, fork, build order, and update rules.
- `third_party/patches/ego-planner-swarm-92fe9f7-local-compat.patch`: recovery copy of the pre-migration 21-file EGO diff.
- `.gitmodules`: pinned team-fork submodule registration.
- `future_aircraft_ws/src/future_aircraft_mission/CMakeLists.txt`: C++ mission package build.
- `future_aircraft_ws/src/future_aircraft_mission/package.xml`: direct ROS dependencies.
- `future_aircraft_ws/src/future_aircraft_mission/include/future_aircraft_mission/ego_setpoint_bridge.hpp`: migrated user header.
- `future_aircraft_ws/src/future_aircraft_mission/src/ego_setpoint_bridge.cpp`: migrated user implementation.
- `future_aircraft_ws/src/future_aircraft_mission/src/ego_setpoint_bridge_node.cpp`: migrated user node entry.
- `sim.ps1`: single public PowerShell command dispatcher.
- `scripts/sim_cli.psm1`: command implementation without lifecycle duplication.
- `scripts/maintenance/clean_logs.ps1`: bounded log cleanup used by `sim.ps1`.
- `scripts/maintenance/curate_pbl1_evidence.py`: deterministic evidence copier and provenance sanitizer.
- `scripts/README.md`: exhaustive script classification.
- `scripts/validate_repository.ps1`: repository/dependency/workspace/CLI contract suite.
- `tests/third_party_dependency_check.py`: submodule and active-reference contract.
- `tests/future_aircraft_mission_package_check.py`: package-boundary contract.
- `tests/developer_workspace_config_check.py`: Catkin and VS Code contract.
- `tests/sim_cli_check.py`: root CLI DryRun and dispatch tests.
- `tests/log_cleanup_check.py`: active-stack and path-boundary cleanup tests.
- `tests/script_inventory_check.py`: every tracked script has exactly one classification.
- `tests/docs_link_check.py`: internal Markdown path/link contract.
- `tests/evidence_snapshot_check.py`: curated PBL-1 evidence contract.
- `docs/README.md`: current documentation index.
- `docs/evidence/pbl1/<run-id>/`: compact evidence for three accepted runs.
- `docs/evidence/2026-08-10-repository-structure-migration.md`: final offline-validation record.

### Modified files

- `.gitignore`: replace ignored `external/` dependency semantics with runtime-only ignores.
- `config/env_template.bat`: point `EGO_SWARM_WSL_DIR` to `third_party`.
- active scripts/config/tests/docs returned by `rg -l "external/ego-planner-swarm|external\\ego-planner-swarm"`.
- `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`: restore protected Python-only baseline.
- `future_aircraft_ws/src/multi_uav_mission/package.xml`: restore protected baseline dependencies.
- `scripts/wsl/build_future_aircraft_ws.sh`: source the `third_party` EGO overlay and support focused package builds.
- `.vscode/tasks.json` and `future_aircraft_ws/.vscode/tasks.json`: expose equivalent public commands.
- `README.md`, `AGENTS.md`, `.agents/AGENT2READ.md`, `.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md`: current paths, ownership, and concise entry guidance.
- lifecycle and Stage validators only where needed to register new repository/CLI contract tests.

### Removed files

- `future_aircraft_ws/src/.gitkeep`
- `scripts/patch_stage4_cmake.ps1`
- `scripts/kill_all.bat`
- `scripts/record_logs.bat`
- `scripts/validate_stage0.ps1`
- `scripts/clone_ego_swarm.bat` after the submodule replacement passes
- `docs/prompts/2026-08-03-continue-stage8-static-map.md`

### Runtime-only removals after all gates pass

- `logs/*`
- all repository `__pycache__/` and `*.pyc`
- `.superpowers/sdd/`
- `.worktrees/stage6d-odometry-stream` and its merged local branch
- old `external/ego-planner-swarm` after its fork commit and new submodule are verified

---

### Task 1: Preserve the EGO Diff and Freeze the Pre-Migration State

**Files:**
- Create: `third_party/README.md`
- Create: `third_party/patches/ego-planner-swarm-92fe9f7-local-compat.patch`
- Reference: `docs/superpowers/specs/2026-08-10-project-structure-optimization-design.md`

**Interfaces:**
- Consumes: current nested repository at `external/ego-planner-swarm`, base commit `92fe9f7227b2da819133eb8e0e8c7fc000f6ae20`.
- Produces: a Git-tracked recovery patch that Task 2 can validate against the fork commit.

- [ ] **Step 1: Reconfirm both dirty worktrees before writing anything**

Run:

```powershell
git status --short --branch
git -C external/ego-planner-swarm status --short --branch
git -C external/ego-planner-swarm rev-parse HEAD
git worktree list --porcelain
```

Expected: root shows the known C++/VS Code/build-script work; EGO reports exactly 21 modified tracked files at `92fe9f7...`; the old Stage 6D worktree is clean and registered. If any additional EGO file appears, stop and add it explicitly to the preservation scope before continuing.

- [ ] **Step 2: Create the dependency policy file**

Create `third_party/README.md` with these exact rules:

```markdown
# Third-party dependencies

Third-party source is not project mission code and is not edited through the
main repository. `ego-planner-swarm` is a separate Catkin overlay pinned as a
Git submodule to the team's fork.

Build order:

1. `/opt/ros/noetic/setup.bash`
2. `third_party/ego-planner-swarm/devel/setup.bash`
3. `future_aircraft_ws/devel/setup.bash`

Dependency updates require a reviewed commit in the dependency repository,
an exact submodule pointer update, the repository contract suite, and the
Stage 6C/6D/7/8 regression suites. Never edit generated `build/` or `devel/`
products as source.
```

- [ ] **Step 3: Export the current EGO diff without shell redirection**

Run:

```powershell
New-Item -ItemType Directory -Force -Path third_party\patches | Out-Null
git -C external/ego-planner-swarm diff --binary --output=../../third_party/patches/ego-planner-swarm-92fe9f7-local-compat.patch
```

Expected: the patch exists in the main repository and contains the 21 modified paths.

- [ ] **Step 4: Verify the patch describes the current checkout exactly**

Run:

```powershell
git -C external/ego-planner-swarm apply --check --reverse ../../third_party/patches/ego-planner-swarm-92fe9f7-local-compat.patch
(Select-String -LiteralPath third_party\patches\ego-planner-swarm-92fe9f7-local-compat.patch -Pattern '^diff --git ').Count
```

Expected: reverse apply check exits 0 and the count is `21`.

- [ ] **Step 5: Commit only the recovery artifacts**

Run:

```powershell
git add -- third_party/README.md third_party/patches/ego-planner-swarm-92fe9f7-local-compat.patch
git diff --cached --check
git diff --cached --name-only
git commit -m "chore: preserve ego planner compatibility patch"
```

Expected: exactly the two named paths are committed; user C++ and editor files remain unstaged.

---

### Task 2: Commit the Team Fork and Pin the EGO Submodule

**Files:**
- Create: `.gitmodules`
- Create: `third_party/ego-planner-swarm` (Git submodule)
- Create: `tests/third_party_dependency_check.py`
- Create: `scripts/validate_repository.ps1`
- Modify: `.gitignore`
- Modify: `config/env_template.bat`
- Modify: `scripts/wsl/build_future_aircraft_ws.sh`
- Modify: files returned by the active-reference searches below
- Remove after tests: `scripts/clone_ego_swarm.bat`

**Interfaces:**
- Consumes: Task 1 recovery patch and the approved team fork URL `https://github.com/s1nyon/ego-planner-swarm.git`.
- Produces: fetchable branch `rflysim-noetic-cxx17-compat`, pinned submodule, `EGO_SWARM_WSL_DIR` at `third_party/ego-planner-swarm`, and `validate_repository.ps1`.

- [ ] **Step 1: Verify the fork exists before changing remotes**

Run:

```powershell
git ls-remote https://github.com/s1nyon/ego-planner-swarm.git
```

Expected: exit 0 and at least one ref. If the repository does not exist or is inaccessible, stop; do not move or delete `external/ego-planner-swarm`.

- [ ] **Step 2: Commit the preserved EGO changes locally**

Run:

```powershell
git -C external/ego-planner-swarm switch -c rflysim-noetic-cxx17-compat
git -C external/ego-planner-swarm add -- src
git -C external/ego-planner-swarm diff --cached --check
git -C external/ego-planner-swarm commit -m "build: support RflySim Noetic C++17 toolchain"
$comparisonPatch = Join-Path ([System.IO.Path]::GetTempPath()) 'ego-planner-swarm-fork-commit.patch'
git -C external/ego-planner-swarm diff HEAD^ --binary --output=$comparisonPatch
git diff --no-index --ignore-space-at-eol -- third_party/patches/ego-planner-swarm-92fe9f7-local-compat.patch $comparisonPatch
Remove-Item -LiteralPath $comparisonPatch
```

Expected: the comparison has no semantic difference; line-ending-only output is acceptable and must be recorded in the task report. The temporary comparison patch is removed immediately after inspection.

- [ ] **Step 3: Add the team remote and pause for explicit push authorization**

Run:

```powershell
git -C external/ego-planner-swarm remote add team https://github.com/s1nyon/ego-planner-swarm.git
git -C external/ego-planner-swarm remote -v
```

Expected: `origin` remains ZJU upstream and `team` is the approved fork. Do not run the next command until the user explicitly authorizes push.

- [ ] **Step 4: Push the compatibility branch after authorization**

Run only after approval:

```powershell
git -C external/ego-planner-swarm push -u team rflysim-noetic-cxx17-compat
git -C external/ego-planner-swarm ls-remote team rflysim-noetic-cxx17-compat
```

Expected: the remote branch resolves to the local EGO HEAD.

- [ ] **Step 5: Write the failing third-party contract test**

Create `tests/third_party_dependency_check.py` so `main()` checks:

```python
EXPECTED_PATH = "third_party/ego-planner-swarm"
EXPECTED_URL = "https://github.com/s1nyon/ego-planner-swarm.git"

# Fail unless .gitmodules declares EXPECTED_PATH and EXPECTED_URL.
# Fail unless config/env_template.bat contains:
#   /future_aircraft_sim/third_party/ego-planner-swarm
# Fail if active files under config/, scripts/, README.md, AGENTS.md, or
# .agents/ contain "external/ego-planner-swarm".
# Fail unless `git submodule status -- third_party/ego-planner-swarm` exits 0
# without a leading '-' or '+'.
```

The test accepts `--project-root`, prints every error with `[FAIL]`, and prints one `[PASS]` line on success.

- [ ] **Step 6: Run the test to verify it fails**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\third_party_dependency_check.py --project-root .
```

Expected: FAIL because `.gitmodules` and the new submodule do not exist.

- [ ] **Step 7: Add the submodule and update active paths**

Run:

```powershell
git submodule add -b rflysim-noetic-cxx17-compat https://github.com/s1nyon/ego-planner-swarm.git third_party/ego-planner-swarm
git -C third_party/ego-planner-swarm checkout (git -C external/ego-planner-swarm rev-parse HEAD)
```

Use `apply_patch` to:

- remove the root `.gitignore` entry `external/`;
- change `EGO_SWARM_WSL_DIR` in `config/env_template.bat` to `/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/third_party/ego-planner-swarm`;
- change active source/build references from `external/ego-planner-swarm` to `third_party/ego-planner-swarm`;
- change obsolete `Run scripts/clone_ego_swarm.bat` guidance to `Run git submodule update --init --recursive and build the EGO workspace`;
- keep historical incident wording only when it explicitly describes the former path;
- update `scripts/wsl/build_future_aircraft_ws.sh` variable `EGO_DEVEL` to `${REPO_ROOT}/third_party/ego-planner-swarm/devel`;
- delete `scripts/clone_ego_swarm.bat` because `git submodule update --init --recursive` is now the supported fetch mechanism.

Run these searches until both active searches are empty:

```powershell
rg -n "external/ego-planner-swarm|external\\ego-planner-swarm" config scripts README.md AGENTS.md .agents
rg -n "external/ego-planner-swarm|external\\ego-planner-swarm" tests
```

- [ ] **Step 8: Create the repository validation entry**

Create `scripts/validate_repository.ps1` with this command order:

```powershell
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
& $python (Join-Path $ProjectRoot 'tests\third_party_dependency_check.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host '[PASS] repository dependency contracts'
exit 0
```

- [ ] **Step 9: Run the focused contracts and EGO build**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
wsl -d RflySim-20.04 -e bash -lic "cd '/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim/third_party/ego-planner-swarm' && source /opt/ros/noetic/setup.bash && catkin_make"
```

Expected: all commands exit 0. Do not remove the old checkout yet.

- [ ] **Step 10: Commit the dependency migration**

Stage `.gitmodules`, the submodule gitlink, `.gitignore`, active path updates, the new test/validator, and deletion of `clone_ego_swarm.bat`. Confirm the staged list contains no user mission source. Commit:

```powershell
git commit -m "build: pin ego planner team fork"
```

---

### Task 3: Separate New C++ Mission Work from the Python Baseline

**Files:**
- Create: `future_aircraft_ws/src/future_aircraft_mission/CMakeLists.txt`
- Create: `future_aircraft_ws/src/future_aircraft_mission/package.xml`
- Create: `future_aircraft_ws/src/future_aircraft_mission/include/future_aircraft_mission/ego_setpoint_bridge.hpp`
- Create: `future_aircraft_ws/src/future_aircraft_mission/src/ego_setpoint_bridge.cpp`
- Create: `future_aircraft_ws/src/future_aircraft_mission/src/ego_setpoint_bridge_node.cpp`
- Create: `tests/future_aircraft_mission_package_check.py`
- Modify: `future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt`
- Modify: `future_aircraft_ws/src/multi_uav_mission/package.xml`
- Modify: `scripts/validate_repository.ps1`
- Remove after byte comparison: `future_aircraft_ws/src/multi_uav_mission/include/ego_setpoint_bridge.hpp`
- Remove after byte comparison: `future_aircraft_ws/src/multi_uav_mission/src/ego_setpoint_bridge.cpp`
- Remove after byte comparison: `future_aircraft_ws/src/multi_uav_mission/src/ego_setpoint_bridge_node.cpp`

**Interfaces:**
- Consumes: EGO's `quadrotor_msgs/PositionCommand` and MAVROS `mavros_msgs/PositionTarget` from the Task 2 overlay.
- Produces: Catkin package `future_aircraft_mission`, library `future_aircraft_mission`, executable `ego_setpoint_bridge_node`.

- [ ] **Step 1: Record hashes of the user C++ files**

Run:

```powershell
Get-FileHash future_aircraft_ws\src\multi_uav_mission\include\ego_setpoint_bridge.hpp -Algorithm SHA256
Get-FileHash future_aircraft_ws\src\multi_uav_mission\src\ego_setpoint_bridge.cpp -Algorithm SHA256
Get-FileHash future_aircraft_ws\src\multi_uav_mission\src\ego_setpoint_bridge_node.cpp -Algorithm SHA256
```

Keep the three hashes in the task report and do not delete the sources until the destination hashes match.

- [ ] **Step 2: Write the failing package-boundary test**

Create `tests/future_aircraft_mission_package_check.py` with assertions equivalent to:

```python
assert (root / "future_aircraft_ws/src/future_aircraft_mission/package.xml").is_file()
assert (root / "future_aircraft_ws/src/future_aircraft_mission/CMakeLists.txt").is_file()
assert "add_library(future_aircraft_mission" in mission_cmake
assert "add_executable(ego_setpoint_bridge_node" in mission_cmake
assert "src/ego_setpoint_bridge.cpp" not in baseline_cmake
assert "<depend>quadrotor_msgs</depend>" in mission_package
assert "<depend>mavros_msgs</depend>" in mission_package
```

It must also compare the source and destination SHA256 hashes when both paths exist and fail on a mismatch.

- [ ] **Step 3: Run the test to verify it fails**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\future_aircraft_mission_package_check.py --project-root .
```

Expected: FAIL because the new package does not exist.

- [ ] **Step 4: Create the new package without changing C++ behavior**

Create `CMakeLists.txt` with these targets and direct dependencies:

```cmake
cmake_minimum_required(VERSION 3.0.2)
project(future_aircraft_mission)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  quadrotor_msgs
  mavros_msgs
)

catkin_package(
  INCLUDE_DIRS include
  LIBRARIES future_aircraft_mission
  CATKIN_DEPENDS roscpp quadrotor_msgs mavros_msgs
)

include_directories(include ${catkin_INCLUDE_DIRS})

add_library(future_aircraft_mission src/ego_setpoint_bridge.cpp)
add_executable(ego_setpoint_bridge_node src/ego_setpoint_bridge_node.cpp)
add_dependencies(future_aircraft_mission ${catkin_EXPORTED_TARGETS})
add_dependencies(ego_setpoint_bridge_node ${catkin_EXPORTED_TARGETS})
target_link_libraries(future_aircraft_mission ${catkin_LIBRARIES})
target_link_libraries(ego_setpoint_bridge_node future_aircraft_mission ${catkin_LIBRARIES})
```

Create `package.xml` with package name `future_aircraft_mission`, version `0.1.0`, `catkin` buildtool dependency, and `<depend>` entries for `roscpp`, `quadrotor_msgs`, and `mavros_msgs`.

Copy the three user files with only this include-path normalization:

```cpp
#include "future_aircraft_mission/ego_setpoint_bridge.hpp"
```

Do not add constructor invocation, timer behavior, command conversion, or other C++ semantics in this restructuring task.

- [ ] **Step 5: Restore the protected package metadata with `apply_patch`**

Restore `multi_uav_mission/CMakeLists.txt` and `package.xml` to the exact `HEAD` baseline recorded before this plan: Python-only `catkin_package()`, the existing `catkin_install_python` list, and only `python3`/`std_srvs` runtime dependencies.

- [ ] **Step 6: Verify hashes, then remove the old C++ locations**

Run `Get-FileHash` for all three destinations. Expected: hashes match the recorded originals except the two files whose include line changed; for those, verify `git diff --no-index` shows only the namespace include-path change. Then remove the old files with `apply_patch`.

- [ ] **Step 7: Register and run the package contract**

Append the new test to `scripts/validate_repository.ps1`, run it, then build:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
wsl -d RflySim-20.04 -e bash -lic "cd '/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim' && bash scripts/wsl/build_future_aircraft_ws.sh --pkg future_aircraft_mission"
```

Expected: repository contracts pass and Catkin reports a successful package build. If the preserved incomplete C++ fails to link, record the exact linker error and stop; do not invent mission behavior in this structural task.

- [ ] **Step 8: Confirm the Python baseline has no task diff**

Run:

```powershell
git diff --name-only -- future_aircraft_ws/src/multi_uav_mission/scripts future_aircraft_ws/src/multi_uav_mission/launch
```

Expected: no output.

- [ ] **Step 9: Commit the package separation**

Stage only the new package, restored baseline metadata, deleted old C++ locations, package test, validator update, and build-script change. Commit:

```powershell
git commit -m "refactor: separate competition mission package"
```

---

### Task 4: Track Developer Workspace Metadata

**Files:**
- Create/track: `.vscode/c_cpp_properties.json`
- Create/track: `.vscode/extensions.json`
- Modify/track: `.vscode/settings.json`
- Modify/track: `.vscode/tasks.json`
- Create/track: `future_aircraft_ws/.catkin_workspace`
- Create/track: `future_aircraft_ws/src/CMakeLists.txt`
- Create/track: `future_aircraft_ws/.vscode/c_cpp_properties.json`
- Create/track: `future_aircraft_ws/.vscode/extensions.json`
- Modify/track: `future_aircraft_ws/.vscode/settings.json`
- Modify/track: `future_aircraft_ws/.vscode/tasks.json`
- Create: `tests/developer_workspace_config_check.py`
- Modify: `scripts/validate_repository.ps1`

**Interfaces:**
- Consumes: the existing WSL build script and the Task 2 `third_party` path.
- Produces: tracked Catkin/IntelliSense metadata and a working build task when opening either repository root or `future_aircraft_ws`.

- [ ] **Step 1: Write the failing workspace-config test**

The test loads both `tasks.json` files as JSON and requires the label `build: future_aircraft_ws` exactly once. It verifies that the root task calls `${workspaceFolder}/scripts/wsl/build_future_aircraft_ws.sh`, while the ROS-workspace task calls `${workspaceFolder}/../scripts/wsl/build_future_aircraft_ws.sh`.

```python
assert root_tasks["build: future_aircraft_ws"]["args"][-1] == (
    "${workspaceFolder}/scripts/wsl/build_future_aircraft_ws.sh"
)
assert ws_tasks["build: future_aircraft_ws"]["args"][-1] == (
    "${workspaceFolder}/../scripts/wsl/build_future_aircraft_ws.sh"
)
```

It also requires `future_aircraft_ws/.catkin_workspace`, `future_aircraft_ws/src/CMakeLists.txt`, root compile commands at `${workspaceFolder}/future_aircraft_ws/build/compile_commands.json`, and ROS-workspace compile commands at `${workspaceFolder}/build/compile_commands.json`.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\developer_workspace_config_check.py --project-root .
```

Expected: FAIL because the current task files use the old build label.

- [ ] **Step 3: Update both task files**

Rename the current build task to `build: future_aircraft_ws`, preserve its direct WSL build-script invocation, and preserve the existing `cwd`, `$gcc` problem matcher, default build group, and dedicated presentation panel. Do not add `sim.ps1` tasks until Task 5 creates that command.

```text
root workspace -> ${workspaceFolder}/scripts/wsl/build_future_aircraft_ws.sh
ROS workspace  -> ${workspaceFolder}/../scripts/wsl/build_future_aircraft_ws.sh
```

Preserve existing IntelliSense include paths, changing only `external/ego-planner-swarm` to `third_party/ego-planner-swarm`.

- [ ] **Step 4: Run and register the test**

Append the test to `scripts/validate_repository.ps1`, then run the validator. Expected: PASS.

- [ ] **Step 5: Commit the workspace metadata**

Stage only both `.vscode` trees, the Catkin marker/top-level file, the test, and validator. Commit:

```powershell
git commit -m "chore: standardize ROS developer workspace"
```

---

### Task 5: Add the Root CLI Core, Doctor, Build, Validation, and VS Code Commands

**Files:**
- Create: `sim.ps1`
- Create: `scripts/sim_cli.psm1`
- Create: `tests/sim_cli_check.py`
- Modify: `.vscode/tasks.json`
- Modify: `future_aircraft_ws/.vscode/tasks.json`
- Modify: `tests/developer_workspace_config_check.py`
- Modify: `scripts/validate_repository.ps1`

**Interfaces:**
- Consumes: `scripts/wsl/build_future_aircraft_ws.sh` and retained validator scripts.
- Produces: `sim.ps1 doctor|build|validate`, module functions `Invoke-SimDoctor`, `Invoke-SimBuild`, and `Invoke-SimValidation`.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/sim_cli_check.py` using `subprocess.run` with `powershell.exe`. Initial cases:

```python
assert run("doctor").returncode in (0, 2)
assert "[doctor]" in run("doctor").stdout
assert run("validate", "-Suite", "invalid").returncode != 0
assert run("unknown-command").returncode != 0
```

The helper must set UTF-8 replacement decoding and a 120-second timeout. The test accepts `--project-root` and executes the repository's real `sim.ps1`.

- [ ] **Step 2: Run the test to verify it fails**

Expected: FAIL because `sim.ps1` does not exist.

- [ ] **Step 3: Create the dispatcher**

Use this parameter contract in `sim.ps1`:

```powershell
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start','status','stop','build','validate','doctor','clean-logs')]
    [string]$Command = 'status',
    [ValidateSet('base','dev')][string]$Profile = 'dev',
    [ValidateSet('mission','core','lifecycle','all')][string]$Suite = 'core',
    [switch]$Execute
)
```

Import `scripts/sim_cli.psm1`, resolve the repository root from `$PSScriptRoot`, dispatch exactly one exported function, and exit with that function's integer result.

- [ ] **Step 4: Implement the module's non-lifecycle functions**

Export these signatures:

```powershell
Invoke-SimDoctor -ProjectRoot <string> -> int
Invoke-SimBuild -ProjectRoot <string> -> int
Invoke-SimValidation -ProjectRoot <string> -Suite <mission|core|lifecycle|all> -> int
```

`doctor` checks, without mutation:

- `D:\PX4PSP\Python38\python.exe` exists and runs;
- WSL distro `RflySim-20.04` exists;
- `third_party/ego-planner-swarm` is an initialized, clean, pinned submodule;
- EGO `devel/setup.bash` exists;
- `future_aircraft_ws/src/CMakeLists.txt` exists;
- `config/env_local.bat` is either absent or readable;
- active configuration contains `/uav1` and `/uav2` namespaces.

Print `[PASS]`, `[WARN]`, or `[FAIL]` per check and return `2` on any failure.

`build` runs `wsl -d RflySim-20.04 -e bash -lic "cd '<repo-wsl-path>' && bash scripts/wsl/build_future_aircraft_ws.sh"` and returns its exit code.

`validate` uses this exact suite mapping:

```powershell
mission   -> scripts\validate_repository.ps1, focused Catkin build --pkg future_aircraft_mission
core      -> validate_stage6c.ps1, validate_stage6d.ps1, validate_stage7.ps1, validate_stage8.ps1
lifecycle -> validate_lifecycle.ps1
all       -> validate_repository.ps1, validate_stage1.ps1, validate_stage2.ps1,
             validate_stage2_1.ps1, validate_stage3.ps1, validate_stage4.ps1,
             validate_stage5.ps1, validate_stage5b.ps1, validate_stage5c.ps1,
             validate_stage5d.ps1, validate_stage5e.ps1, validate_stage6a.ps1,
             validate_stage6b.ps1, validate_stage6c.ps1, validate_stage6d.ps1,
             validate_stage7.ps1, validate_stage8.ps1, validate_lifecycle.ps1
```

Stop on the first nonzero result and print the failed script path.

- [ ] **Step 5: Run the CLI and repository tests**

Before running the tests, add these labels to both task files while retaining `build: future_aircraft_ws`:

```text
sim: doctor          -> sim.ps1 doctor
sim: start (dry-run) -> sim.ps1 start
sim: status          -> sim.ps1 status
sim: stop (dry-run)  -> sim.ps1 stop
validate: core       -> sim.ps1 validate -Suite core
```

For the root workspace use `${workspaceFolder}/sim.ps1`; for the ROS workspace use `${workspaceFolder}/../sim.ps1`. Invoke each through `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`. Extend `developer_workspace_config_check.py` to require all six final labels.

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\sim_cli_check.py --project-root .
.\sim.ps1 doctor
.\sim.ps1 validate -Suite mission
```

Expected: CLI contract PASS; doctor returns 0 in the configured machine; mission suite passes.

- [ ] **Step 6: Register and commit**

Add `tests/sim_cli_check.py` to `validate_repository.ps1`. Commit only the CLI, module, both task files, both updated tests, and validator:

```powershell
git commit -m "feat: add repository simulation command"
```

---

### Task 6: Add Fail-Closed Start, Status, and Stop Delegation

**Files:**
- Modify: `scripts/sim_cli.psm1`
- Modify: `tests/sim_cli_check.py`
- Test fixtures created only in temporary directories by the test

**Interfaces:**
- Consumes: `live_stack_start.ps1`, `live_stack_inspect.ps1`, `end_live_stack.ps1`, Stage 7 runners, and manifest schema v2.
- Produces: module functions `Resolve-ActiveStackManifest`, `Invoke-SimStart`, `Invoke-SimStatus`, `Invoke-SimStop`.

- [ ] **Step 1: Add failing manifest-resolution tests**

Generate temporary `logs/live_stack/<stack-id>/stack_manifest.json` fixtures with `schema_version=2` and these cases:

```python
closed = {"stack_id": "stack-closed", "stop": {"clean": True}}
active = {"stack_id": "stack-active", "stop": {"clean": False}}
```

Invoke PowerShell to import `scripts/sim_cli.psm1` and call `Resolve-ActiveStackManifest -ProjectRoot <temp-root>`. Assert:

- no candidate returns an empty result and exit 0;
- one non-clean candidate returns its manifest path;
- two non-clean candidates fail with `multiple active stack manifests`;
- malformed JSON fails and does not select another manifest.

- [ ] **Step 2: Run the focused tests to verify failure**

Expected: FAIL because the resolver is not exported.

- [ ] **Step 3: Implement active-manifest resolution**

Export:

```powershell
Resolve-ActiveStackManifest -ProjectRoot <string> -> FileInfo|null
```

Enumerate only direct children of `<ProjectRoot>\logs\live_stack`. A manifest is closed only when parsed JSON contains `stop.clean -eq $true`. Treat missing `stop`, `clean=false`, invalid JSON, and unreadable files as unresolved active state. Return one candidate, return null for none, and throw for more than one or malformed data.

- [ ] **Step 4: Add failing DryRun dispatch tests**

Assert the real repository commands:

```python
start = run("start")
assert start.returncode == 0
assert "[DRY-RUN]" in start.stdout

stop = run("stop")
assert stop.returncode in (0, 2)
assert "DryRun" in stop.stdout or "no active stack" in stop.stdout
```

Also statically assert that `sim_cli.psm1` references the three protected wrappers and contains none of `wsl --shutdown`, `pkill -9`, `taskkill /F`, or `Stop-Process -Force`.

- [ ] **Step 5: Implement protected delegation**

Export:

```powershell
Invoke-SimStart  -ProjectRoot <string> -Profile <base|dev> -Execute <bool> -> int
Invoke-SimStatus -ProjectRoot <string> -> int
Invoke-SimStop   -ProjectRoot <string> -Execute <bool> -> int
```

Behavior:

- `start` DryRun calls `scripts/live_stack_start.ps1 -DryRun`, then prints the selected profile stages.
- `start -Execute` refuses when `Resolve-ActiveStackManifest` returns a candidate; otherwise calls `live_stack_start.ps1 -Execute`.
- `base` returns after the existing health gate succeeds.
- `dev` records the existing `logs/stage7_live/current_run.env` run ID and write time, calls `run_live_fastlio_dual.bat`, and waits up to 180 seconds for `current_run.env` to contain a different run ID and its referenced `sensor_readiness.json` to exist. It then calls `run_live_ego_swarm_dual.bat`; that protected runner performs the authoritative `stage7_sensor_readiness.py --validate` check before launching EGO.
- Any failed stage returns nonzero and prints the exact failed stage; it never stops or retries automatically.
- `status` prints `no active stack` when none exists; otherwise calls `live_stack_inspect.ps1 -Manifest <path>`.
- `stop` with no candidate prints `no active stack` and returns 0.
- `stop` DryRun calls `end_live_stack.ps1 -Manifest <path> -DryRun`.
- `stop -Execute` calls `end_live_stack.ps1 -Manifest <path>` and propagates its exit code.

- [ ] **Step 6: Run focused and lifecycle contracts**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\sim_cli_check.py --project-root .
.\sim.ps1 start
.\sim.ps1 status
.\sim.ps1 stop
powershell -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
```

Expected: all DryRun/read-only checks and lifecycle validation pass. Do not use `-Execute` in this task.

- [ ] **Step 7: Commit**

```powershell
git add -- scripts/sim_cli.psm1 tests/sim_cli_check.py
git diff --cached --check
git commit -m "feat: delegate safe live stack commands"
```

---

### Task 7: Add Bounded Log Cleanup

**Files:**
- Create: `scripts/maintenance/clean_logs.ps1`
- Create: `tests/log_cleanup_check.py`
- Modify: `scripts/sim_cli.psm1`
- Modify: `scripts/validate_repository.ps1`

**Interfaces:**
- Consumes: Task 6 active-manifest resolver.
- Produces: `Invoke-SimLogCleanup` and a standalone maintenance script that never deletes active-stack or out-of-root paths.

- [ ] **Step 1: Write failing cleanup tests**

Use temporary project roots and invoke the PowerShell script. Cover:

1. DryRun lists files but leaves them present.
2. Execute with a non-clean stack manifest exits 2 and leaves every file present.
3. Execute with only `stop.clean=true` manifests deletes children under `<root>/logs` but not the `logs` directory.
4. A junction/symlink or resolved child outside `<root>/logs` causes failure before deletion.
5. A missing `logs` directory returns 0.

- [ ] **Step 2: Run the tests to verify failure**

Expected: FAIL because the maintenance script does not exist.

- [ ] **Step 3: Implement the cleanup script**

Use parameters:

```powershell
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [switch]$Execute
)
```

Resolve `<ProjectRoot>\logs` to an absolute path, verify its parent is exactly the resolved project root, reject any non-clean/malformed stack manifest, enumerate each direct child, resolve it, confirm it remains under the log root, print `[DRY-RUN] remove <path>` by default, and use `Remove-Item -LiteralPath <verified-child> -Recurse -Force` only with `-Execute`. Never accept an arbitrary target path.

- [ ] **Step 4: Wire `sim.ps1 clean-logs`**

Export `Invoke-SimLogCleanup -ProjectRoot <string> -Execute <bool> -> int` from the module and delegate to the maintenance script. Preserve the root command's default DryRun behavior.

- [ ] **Step 5: Run and register tests**

Run the focused test, `.\sim.ps1 clean-logs`, and `validate_repository.ps1`. Expected: PASS; real repository logs remain untouched because `-Execute` is absent.

- [ ] **Step 6: Commit**

```powershell
git commit -m "feat: add guarded log maintenance"
```

---

### Task 8: Reorganize Current Documentation and Remove Obsolete Scaffolding

**Files:**
- Create: `docs/README.md`
- Create: `scripts/README.md`
- Create: `tests/script_inventory_check.py`
- Create: `tests/docs_link_check.py`
- Move: `docs/competition-roadmap.md` -> `docs/current/competition-roadmap.md`
- Move: `docs/d435i_sensor_parity_2026-08-07.md` -> `docs/current/d435i_sensor_parity_2026-08-07.md`
- Move: `docs/2026-08-08-live-stack-lifecycle-design.md` -> `docs/architecture/2026-08-08-live-stack-lifecycle-design.md`
- Move: `docs/2026-08-08-lifecycle-p0-fix-live-validated.md` -> `docs/evidence/2026-08-08-lifecycle-p0-fix-live-validated.md`
- Move: `docs/2026-08-08-pbl1-fullstack-regression-closure.md` -> `docs/evidence/2026-08-08-pbl1-fullstack-regression-closure.md`
- Move: `docs/2026-08-08-cleanup-script-hazard.md` -> `docs/incidents/2026-08-08-cleanup-script-hazard.md`
- Move: `docs/2026-08-08-live-stack-dual-coptersim-findings.md` -> `docs/incidents/2026-08-08-live-stack-dual-coptersim-findings.md`
- Move: `docs/stage4_ego_swarm_status.md` -> `docs/incidents/stage4_ego_swarm_status.md`
- Move: `docs/stage8_lidar_issue_2026-08-02.md` -> `docs/incidents/stage8_lidar_issue_2026-08-02.md`
- Move: `docs/stage8_tunnel_live_issue_2026-08-02.md` -> `docs/incidents/stage8_tunnel_live_issue_2026-08-02.md`
- Move: `第十二届中国研究生未来飞行器创新大赛参赛指南.pdf` -> `docs/reference/competition-guide-2026.pdf`
- Modify: `README.md`, `AGENTS.md`, `.agents/AGENT2READ.md`, `.agents/RFLYSIM_TOOLCHAIN_REFERENCE.md`
- Modify: `scripts/validate_repository.ps1` and all affected document links
- Remove: the seven obsolete tracked files listed in the file map

**Interfaces:**
- Consumes: all retained public/protected/focused scripts.
- Produces: concise current documentation and a machine-checked script inventory.

- [ ] **Step 1: Write the failing script inventory test**

The test runs `git ls-files scripts`, excludes `scripts/README.md`, extracts backtick paths from the five classification tables in `scripts/README.md`, and fails unless every tracked script appears exactly once. Allowed categories are exactly:

```python
CATEGORIES = {
    "Public entry",
    "Protected internal",
    "Focused diagnostic",
    "Hazard-disabled",
    "Historical compatibility",
}
```

- [ ] **Step 2: Write the failing documentation-link test**

Scan tracked Markdown files, resolve relative Markdown links that are not `http`, `https`, or anchors, and fail when the referenced local file does not exist. Explicitly check that active documents reference `docs/current/competition-roadmap.md` and `docs/reference/competition-guide-2026.pdf`.

- [ ] **Step 3: Run both tests to verify failure**

Expected: FAIL because the indexes and destination paths do not exist.

- [ ] **Step 4: Move documents with `git mv` and update links**

Create destination directories, perform the exact moves listed above, and update all tracked references with `apply_patch`. Preserve `docs/superpowers/` and `docs/decisions/` in place. Delete the superseded UE Editor prompt.

- [ ] **Step 5: Rewrite the current entry documents**

`README.md` must contain these sections only: Competition Goal, Current Capability, Repository Layout, Quick Start, Safety, Development Ownership, Validation, Documentation Index.

`AGENTS.md` retains all live red-zone and arming rules, adds the human/Agent ownership boundary, and points historical diagnosis to `docs/incidents/`.

`.agents/AGENT2READ.md` is reduced to these sections: Current Truth, Five-Minute Entry Check, Architecture, Ownership, Protected Baseline, Task Routing, Testing Ladder, Live Entry Commands, Truth Priority, Handoff Format. Historical incident narratives move to the incident documents rather than remaining duplicated.

`docs/README.md` links each current, architecture, evidence, incident, decision, reference, and superpowers directory and states which documents can define Current Truth.

- [ ] **Step 6: Delete obsolete scaffolding**

Delete with `apply_patch`:

```text
future_aircraft_ws/src/.gitkeep
scripts/patch_stage4_cmake.ps1
scripts/kill_all.bat
scripts/record_logs.bat
scripts/validate_stage0.ps1
```

`scripts/clone_ego_swarm.bat` was already deleted in Task 2. Keep `create_log_run.bat` because the Stage 3→5→6 validator chain still consumes it. Keep both hazard-disabled lifecycle tombstones.

- [ ] **Step 7: Build the exhaustive script index**

Classify every retained tracked path. At minimum:

- Public entry: `live_stack_start.ps1`, `live_stack_inspect.ps1`, `live_stack_stop.ps1`, `live_stack_fresh_instance.ps1`, `end_live_stack.ps1`, Stage 7 runner BAT files, validators.
- Protected internal: `lifecycle/*`, live-used `wsl/*`, current map/start helper BAT files.
- Focused diagnostic: Stage 1/2/2.1/4 helpers, probes, recorder, focused validators.
- Hazard-disabled: `cleanup_sim_stack.ps1`, `restart_live_stack.ps1`.
- Historical compatibility: retained early-stage wrappers still required by regression chains.

The inventory test, not this minimum list, determines completeness.

- [ ] **Step 8: Run documentation and regression checks**

Append `tests/script_inventory_check.py` and `tests/docs_link_check.py` to `scripts/validate_repository.ps1` before running the commands.

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\script_inventory_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
```

Expected: all pass.

- [ ] **Step 9: Commit**

```powershell
git commit -m "docs: clarify current project structure"
```

---

### Task 9: Curate PBL-1 Evidence and Perform Approved Runtime Cleanup

**Files:**
- Create: `scripts/maintenance/curate_pbl1_evidence.py`
- Create: `tests/evidence_snapshot_check.py`
- Create: seven evidence files under each of:
  - `docs/evidence/pbl1/stage7-20260807T133813Z-2617/`
  - `docs/evidence/pbl1/stage7-20260807T134731Z-2508/`
  - `docs/evidence/pbl1/stage7-20260807T141751Z-3219/`
- Modify: `scripts/validate_repository.ps1`
- Runtime remove after gates: logs, caches, old worktree, old external checkout, `.superpowers/sdd`

**Interfaces:**
- Consumes: three accepted run directories and Task 7 bounded cleanup.
- Produces: compact tracked evidence and a clean runtime workspace.

- [ ] **Step 1: Write the failing evidence test**

Require exactly these seven files per run:

```python
REQUIRED = {
    "sensor_readiness.json",
    "flight_report.json",
    "score_summary.json",
    "provenance.json",
    "executor_trace.json",
    "mission_events.jsonl",
    "slam_ego_swarm_smoke_report.json",
}
```

Assert `score_summary.success is True`, both UAVs have arming/navigation/landing confirmation in `flight_report.json`, readiness errors are empty, provenance run ID equals the directory name, and `course_spec` equals `config/maps/predicted_narrow_course_v1.json` rather than an absolute machine path.

- [ ] **Step 2: Run the evidence test to verify failure**

Expected: FAIL because curated directories do not exist.

- [ ] **Step 3: Implement the deterministic curator**

Use command contract:

```text
python curate_pbl1_evidence.py --logs-root <repo>/logs/stage7_live --output-root <repo>/docs/evidence/pbl1
```

Hard-code the three approved run IDs and seven allowed file names. Refuse a missing source, unexpected symlink, failed score, readiness error, or output outside the resolved output root. Copy JSON/JSONL content and replace only `provenance.course_spec` with `config/maps/predicted_narrow_course_v1.json`; preserve all other fields. Do not copy `.log` files.

- [ ] **Step 4: Generate and validate evidence**

Append `tests/evidence_snapshot_check.py` to `scripts/validate_repository.ps1`. Run the curator, focused test, and `validate_repository.ps1`. Inspect `rg -n "D:\\\\|/mnt/[a-z]/|PC-202|Administrator" docs/evidence/pbl1`; expected: no output.

- [ ] **Step 5: Reconfirm destructive cleanup gates**

Run:

```powershell
.\sim.ps1 status
git -C third_party/ego-planner-swarm status --short --branch
git ls-remote https://github.com/s1nyon/ego-planner-swarm.git rflysim-noetic-cxx17-compat
git worktree list --porcelain
git -C .worktrees/stage6d-odometry-stream status --short --branch
git merge-base --is-ancestor stage6d-odometry-stream main
```

Required before deletion: no active stack, new submodule clean, fork branch fetchable at the pinned commit, old worktree clean, and ancestor check exit 0.

- [ ] **Step 6: Remove the old registered worktree safely**

Run:

```powershell
git worktree remove -- .worktrees/stage6d-odometry-stream
git branch -d stage6d-odometry-stream
git worktree list --porcelain
```

Expected: old path and merged local branch are gone; main worktree remains.

- [ ] **Step 7: Clean logs using the guarded command**

Run `.\sim.ps1 clean-logs` and review every listed target. Then run `.\sim.ps1 clean-logs -Execute`. Expected: `logs/` exists and is empty or recreated on demand; `docs/evidence/pbl1` remains intact.

- [ ] **Step 8: Remove caches and the old EGO checkout with verified paths**

In one PowerShell session, resolve each target and assert it is beneath the project root before removal. Targets are `.superpowers/sdd`, repository `__pycache__` directories, `.pyc` files, and `external/ego-planner-swarm`. Do not remove `future_aircraft_ws/build`, `future_aircraft_ws/devel`, `third_party/ego-planner-swarm`, or `generated`.

After removal, run:

```powershell
Test-Path external\ego-planner-swarm
rg --files -uu -g '**/__pycache__/**' -g '*.pyc' -g '!.git/**' -g '!third_party/**'
```

Expected: `False` and no cache-file output.

- [ ] **Step 9: Commit tracked evidence and maintenance code**

```powershell
git commit -m "chore: curate baseline evidence and runtime cleanup"
```

Runtime deletions are ignored and therefore will not appear in the commit.

---

### Task 10: Run the Full Offline Gate and Record the Migration

**Files:**
- Create: `docs/evidence/2026-08-10-repository-structure-migration.md`

**Interfaces:**
- Consumes: Tasks 1-9.
- Produces: auditable offline completion evidence and an explicit statement of remaining live risk.

- [ ] **Step 1: Verify repository and submodule state**

Run:

```powershell
git status --short --branch
git submodule status
git -C third_party/ego-planner-swarm status --short --branch
git diff --check
rg -n "external/ego-planner-swarm|external\\ego-planner-swarm" config scripts tests README.md AGENTS.md .agents
git diff --name-only 49bf7f7..HEAD -- future_aircraft_ws/src/multi_uav_mission/scripts future_aircraft_ws/src/multi_uav_mission/launch
```

Expected: submodule is pinned without `-`, `+`, or dirty state; active old-path search and protected Python/launch diff are empty. Record `49bf7f7` as the pre-implementation design baseline in the evidence document.

- [ ] **Step 2: Run repository, CLI, and build gates**

Run:

```powershell
.\sim.ps1 doctor
.\sim.ps1 build
.\sim.ps1 validate -Suite mission
.\sim.ps1 start
.\sim.ps1 status
.\sim.ps1 stop
.\sim.ps1 clean-logs
```

Expected: doctor/build/mission pass; all state-changing commands remain DryRun; status is read-only.

- [ ] **Step 3: Run protected offline regression suites**

Run in this order:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_lifecycle.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6c.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage6d.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage7.ps1
powershell -ExecutionPolicy Bypass -File scripts\validate_stage8.ps1
```

Expected: every command exits 0. A failure blocks completion; fix the responsible task and rerun the entire sequence.

- [ ] **Step 4: Write the migration evidence document**

Record:

- root commit range;
- EGO fork URL, branch, and pinned commit;
- files deleted and runtime directories cleaned;
- exact commands and exit codes from Steps 1-3;
- statement that `multi_uav_mission` Python/launch files were unchanged;
- statement `Offline structure migration validated; live no-arm parity not yet verified` unless a separately authorized no-arm run has occurred;
- rollback points for dependency, package, CLI, and docs commits.

- [ ] **Step 5: Run final documentation and diff checks**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\script_inventory_check.py --project-root .
git diff --check
git status --short
```

Expected: tests pass, diff check is clean, and status contains only the migration evidence document before its commit.

- [ ] **Step 6: Commit the evidence**

```powershell
git add -- docs/evidence/2026-08-10-repository-structure-migration.md
git diff --cached --check
git commit -m "docs: record repository structure migration"
```

- [ ] **Step 7: Present the live no-arm decision separately**

Do not execute a live stack. Report the offline result and ask whether the user wants a separately supervised `sim.ps1 start -Execute` no-arm parity check. Any real stop remains subject to the manifest ownership review and explicit execution authorization in `AGENTS.md`.
