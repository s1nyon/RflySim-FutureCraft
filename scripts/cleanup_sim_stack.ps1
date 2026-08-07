param(
    [switch]$DryRun
)

# HAZARD-DISABLED
#
# 2026-08-08 P0: this entry point is permanently disabled after the live-stack
# hard-cleanup incident (BSOD). The old body force-killed RflySim3D/CopterSim/QGC
# by name, sent SIGKILL across the whole WSL chain, ran a WSL distribution-level
# shutdown, and deleted/recreated the Session-1 scheduled task.
#
# Nothing in this file may ever stop a process. Safe alternatives:
#   scripts\live_stack_inspect.ps1 -Manifest <logs/live_stack/<stack_id>/stack_manifest.json>
#   scripts\live_stack_stop.ps1 -Manifest <...> -DryRun
#   scripts\live_stack_fresh_instance.ps1 -DryRun

Write-Host '[HAZARD-DISABLED] cleanup_sim_stack.ps1 is disabled (P0 live-stack lifecycle).' -ForegroundColor Red
Write-Host '[HAZARD-DISABLED] It must never force-stop processes by name, kill WSL chains, or shut down WSL.' -ForegroundColor Red
Write-Host '[HAZARD-DISABLED] Use the manifest-based safe lifecycle entries instead (see header).' -ForegroundColor Red
if ($DryRun) {
    Write-Host '[HAZARD-DISABLED] -DryRun requested; nothing would have been done anyway.' -ForegroundColor Yellow
}
exit 1
