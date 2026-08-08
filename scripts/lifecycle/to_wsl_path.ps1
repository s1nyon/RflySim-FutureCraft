param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$OutFile
)

# Deterministic Windows -> WSL path conversion used by the launch chain. The
# result is written to OutFile (ASCII) so batch callers can read it back with
# `for /f`; this replaces the old inline `-Command` + `set /p` pattern that had
# no fail-fast and could stall on console input when the file was missing/empty.
$ErrorActionPreference = 'Stop'

function ConvertTo-WslPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($Path -match '^[A-Za-z]:\\') {
        $drive = $Path.Substring(0, 1).ToLowerInvariant()
        $rest = $Path.Substring(2).Replace('\', '/')
        return "/mnt/$drive$rest"
    }
    if ($Path.StartsWith('/')) {
        return $Path.Replace('\', '/')
    }
    throw "cannot convert '$Path' to a WSL path (not a Windows drive path and not already a WSL path)"
}

try {
    $wsl = ConvertTo-WslPath -Path $Path
} catch {
    Write-Error "to_wsl_path: $($_.Exception.Message)"
    exit 1
}
if ([string]::IsNullOrWhiteSpace($wsl)) {
    Write-Error "to_wsl_path: converted path is empty for '$Path'"
    exit 1
}
Set-Content -LiteralPath $OutFile -Value $wsl -Encoding ASCII
Write-Output "converted '$Path' -> '$wsl'"
exit 0
