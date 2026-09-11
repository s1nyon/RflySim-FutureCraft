# README Homepage Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository homepage with the prepared bilingual RflySim FutureCraft README and its referenced image assets on every branch currently published by `origin`.

**Architecture:** Treat `RflySim-FutureCraft-README/` as a temporary import bundle. Copy its two homepage documents and README asset directory into their repository-native destinations, verify byte parity and local links, then remove the temporary bundle without importing `.DS_Store` metadata.

**Tech Stack:** Markdown, JPEG/PNG assets, PowerShell, repository Python validators, Git.

## Global Constraints

- Do not modify simulator, lifecycle, ROS, mission, planner, sensor, arming, or flight-baseline behavior.
- Preserve the existing unrelated modification in `future_aircraft_ws/src/future_aircraft_mission/src/mission_manager.cpp`.
- Do not import `.DS_Store` files.
- The user explicitly authorized updating every remote branch on 2026-09-11.
- Never force push; each remote update must be a normal fast-forward push.

---

### Task 1: Import the bilingual homepage and assets

**Files:**
- Modify: `README.md`
- Create: `README.zh-CN.md`
- Create: `docs/assets/readme/README.md`
- Create: `docs/assets/readme/hero.png`
- Create: `docs/assets/readme/corridor-flight.jpg`
- Create: `docs/assets/readme/dual-uav-corridor.jpg`
- Create: `docs/assets/readme/dual-uav-platforms.jpg`

**Interfaces:**
- Consumes: prepared files under `RflySim-FutureCraft-README/`.
- Produces: root bilingual README entry points whose image URLs resolve under `docs/assets/readme/`.

- [ ] **Step 1: Record source hashes**

Run `Get-FileHash` with SHA-256 for the two README files and five files under `docs/assets/readme/`.

- [ ] **Step 2: Copy the prepared files**

Use exact-file copies for both README files and a recursive mechanical copy for `docs/assets/readme/`. Exclude both `.DS_Store` files from all destinations.

- [ ] **Step 3: Verify destination parity**

Run `Get-FileHash` on each source/destination pair and require all seven pairs to match.

- [ ] **Step 4: Review the documentation diff**

Run `git diff -- README.md README.zh-CN.md docs/assets/readme` and `git status --short`. Confirm `mission_manager.cpp` remains modified but unstaged and no `.DS_Store` is present.

### Task 2: Validate and finalize the import

**Files:**
- Delete after parity verification: `RflySim-FutureCraft-README/`
- Modify: `docs/superpowers/plans/2026-09-11-readme-homepage-replacement.md` checkbox state only if useful for execution tracking

**Interfaces:**
- Consumes: the imported files from Task 1.
- Produces: a repository homepage whose local links and repository structure validators pass, with no temporary import bundle left behind.

- [ ] **Step 1: Run focused documentation checks**

Run:

```powershell
D:\PX4PSP\Python38\python.exe tests\script_inventory_check.py --project-root .
D:\PX4PSP\Python38\python.exe tests\docs_link_check.py --project-root .
```

Expected: both commands exit `0`.

- [ ] **Step 2: Run repository validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_repository.ps1
```

Expected: exit `0` with all repository checks passing.

- [ ] **Step 3: Remove the verified temporary bundle**

Resolve the absolute path of `RflySim-FutureCraft-README/`, confirm it is a direct child of the repository root, then remove only that directory recursively. Confirm the path no longer exists.

- [ ] **Step 4: Perform the final safety review**

Run `git status --short`, `git diff --check`, and search tracked/untracked paths for `.DS_Store`. Confirm only the planned documentation import, this plan, and the pre-existing `mission_manager.cpp` modification are present.

- [ ] **Step 5: Commit only the homepage import**

Stage `README.md`, `README.zh-CN.md`, and `docs/assets/readme/`. Verify the staged file list contains only homepage content, then commit with message `docs: replace project homepage`.

### Task 3: Propagate the homepage commit to every remote branch

**Files:**
- Modify on each remote branch: `README.md`
- Create on each remote branch: `README.zh-CN.md`
- Create on each remote branch: `docs/assets/readme/README.md` and four image assets

**Interfaces:**
- Consumes: the pure homepage commit produced by Task 2 and the live branch list returned by `git ls-remote --heads origin`.
- Produces: one normal fast-forward update per remote branch, each containing the same homepage payload.

- [ ] **Step 1: Refresh and freeze the branch set**

Run `git fetch --prune origin` and `git ls-remote --heads origin`. Record the branch names and current object IDs immediately before propagation.

- [ ] **Step 2: Apply the homepage commit in isolated temporary worktrees**

For each remote branch other than the current branch, create a temporary detached worktree at its recorded `origin/<branch>` tip and cherry-pick the pure homepage commit. Stop that branch on any conflict; do not resolve by discarding branch-specific content.

- [ ] **Step 3: Validate each candidate branch**

In each temporary worktree, run `tests/docs_link_check.py --project-root .` and `git diff --check HEAD^ HEAD`. Require both to exit `0` before pushing that branch.

- [ ] **Step 4: Push each branch without force**

Push with `git push origin HEAD:refs/heads/<branch>`. A non-fast-forward or protection rejection is a fail-closed result for that branch; do not retry with `--force`.

- [ ] **Step 5: Verify all remote branch payloads**

Fetch the updated remote refs, then for each remote branch compare the Git blob IDs of `README.md`, `README.zh-CN.md`, and the five `docs/assets/readme/` files. Require all seven blob IDs to match across all branches.

- [ ] **Step 6: Remove temporary worktrees and report results**

Remove only the explicitly created temporary worktree paths using `git worktree remove`. Report the pushed commit ID for every remote branch and any branch that failed closed.
