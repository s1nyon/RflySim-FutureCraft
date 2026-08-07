param(
    [switch]$DryRun
)

# HAZARD-DISABLED
#
# 2026-08-08 P0: this entry point is permanently disabled after the live-stack
# hard-cleanup incident (BSOD). The old body invoked cleanup_sim_stack.ps1
# (name-based force kills + WSL chain SIGKILL + WSL distribution-level shutdown)
# and then recreated/ran the Session-1 scheduled task as a retry mechanism.
#
# Fresh-instance restarts must now go through the gated lifecycle sequence:
#   scripts\live_stack_fresh_instance.ps1 -DryRun
# which inspects -> gracefully stops owned processes -> verifies clean ->
# starts a NEW stack with a NEW stack_id -> health gate -> readiness -> flight.

Write-Host '[HAZARD-DISABLED] restart_live_stack.ps1 is disabled (P0 live-stack lifecycle).' -ForegroundColor Red
Write-Host '[HAZARD-DISABLED] It must never chain a hard cleanup into a scheduled-task restart.' -ForegroundColor Red
Write-Host '[HAZARD-DISABLED] Use scripts\live_stack_fresh_instance.ps1 (DryRun first).' -ForegroundColor Red
if ($DryRun) {
    Write-Host '[HAZARD-DISABLED] -DryRun requested; nothing would have been done anyway.' -ForegroundColor Yellow
}
exit 1
