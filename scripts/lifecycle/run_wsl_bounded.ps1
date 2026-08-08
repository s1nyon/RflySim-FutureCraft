param(
    [Parameter(Mandatory = $true)][string]$Distro,
    [Parameter(Mandatory = $true)][string]$Command,
    [int]$TimeoutSeconds = 240
)

# Run a WSL command with a hard fail-fast deadline. The wsl.exe child is created
# by THIS process (owned at creation); on timeout it is stopped by explicit PID
# (never by name) and the caller receives a non-zero exit code instead of an
# unbounded hang. Used for the Stage 2 health-gate wait in
# start_wsl_mavros_two.bat.
$ErrorActionPreference = 'Stop'

$proc = Start-Process -FilePath 'wsl.exe' `
    -ArgumentList @('-d', $Distro, '-e', 'bash', '-lic', $Command) `
    -WindowStyle Hidden -PassThru
if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    try {
        Stop-Process -Id $proc.Id -ErrorAction SilentlyContinue
    } catch {
        # The child already exited between the timeout check and now.
    }
    Write-Error "run_wsl_bounded: WSL command timed out after ${TimeoutSeconds}s"
    exit 124
}
exit $proc.ExitCode
