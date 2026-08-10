# Live Import and PowerShell Compatibility Design

## Goal

Restore the protected `dev` no-arm chain and then run one explicitly authorized simulation-only armed flight without changing mission strategy, planner tuning, vehicle namespaces, or safety gates.

## Design

1. Make `rflysim_pointcloud_adapter.py` resolve its sibling pure-Python helper from the source `scripts` directory before Catkin's generated `devel/lib` relay directory. This fixes the observed `convert_cloud` import shadowing while leaving cloud conversion behavior unchanged.
2. Make the root CLI accept JSON schema version `2` independent of whether `ConvertFrom-Json` returns `Int32` (Windows PowerShell 5.1) or `Int64` (PowerShell 7). All other manifest shape, containment, name, and stop-state checks remain fail-closed.
3. Add focused regressions first, observe them fail, then implement only the two fixes.

## Validation and Safety

- Run focused adapter-import and CLI tests, lifecycle validation, Stage 7/8 validators, and the mission suite.
- Start the `dev` profile and require fresh dual-sensor/Faster-LIO/EGO readiness.
- Only then invoke the protected flight runner with both `--simulation-only` and `--allow-arm`; the existing arm policy and run/instance identity checks remain authoritative.
- Stop only processes owned by the current stack manifest, after DryRun inspection. Unknown ownership, stale PID identity, readiness failure, or policy failure stops the procedure without force retry.

## Rollback

Revert the two production edits and their focused tests. Runtime logs are ignored artifacts and do not alter the repository baseline.
