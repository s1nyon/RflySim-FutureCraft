[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.Length -gt $root.Length) {
        return $fullPath.TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    }
    return $fullPath
}

function Resolve-FinalItemPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$Visited = @()
    )

    $resolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $normalizedPath = Get-NormalizedPath -Path $resolvedPath
    if ($Visited -contains $normalizedPath) {
        throw "reparse-point cycle detected: $normalizedPath"
    }

    $item = Get-Item -LiteralPath $normalizedPath -Force -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) {
        return $normalizedPath
    }

    $targets = @($item.Target | Where-Object { $null -ne $_ -and "$_".Trim() })
    if ($targets.Count -ne 1) {
        throw "reparse point has no unique target: $normalizedPath"
    }
    $targetPath = "$($targets[0])"
    if (-not [System.IO.Path]::IsPathRooted($targetPath)) {
        $targetPath = Join-Path (Split-Path -Parent $normalizedPath) $targetPath
    }
    return Resolve-FinalItemPath -Path $targetPath -Visited ($Visited + $normalizedPath)
}

function Test-PathEqual {
    param(
        [Parameter(Mandatory = $true)][string]$Left,
        [Parameter(Mandatory = $true)][string]$Right
    )

    return [string]::Equals(
        (Get-NormalizedPath -Path $Left),
        (Get-NormalizedPath -Path $Right),
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Test-PathContained {
    param(
        [Parameter(Mandatory = $true)][string]$Child,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $normalizedChild = Get-NormalizedPath -Path $Child
    $normalizedParent = Get-NormalizedPath -Path $Parent
    $prefix = $normalizedParent + [System.IO.Path]::DirectorySeparatorChar
    return $normalizedChild.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-CleanStackManifests {
    param(
        [Parameter(Mandatory = $true)][string]$LogRoot,
        [Parameter(Mandatory = $true)][object[]]$VerifiedChildren
    )

    $liveStack = @($VerifiedChildren | Where-Object { $_.Item.Name -eq 'live_stack' })
    if ($liveStack.Count -eq 0) {
        return
    }
    if ($liveStack.Count -ne 1 -or -not $liveStack[0].Item.PSIsContainer) {
        throw "malformed live stack manifest root: $(Join-Path $LogRoot 'live_stack')"
    }

    $manifestRoot = $liveStack[0].ResolvedPath
    foreach ($stackDirectory in @(Get-ChildItem -LiteralPath $liveStack[0].Item.FullName -Force -ErrorAction Stop)) {
        if (-not $stackDirectory.PSIsContainer) {
            throw "malformed stack manifest entry is not a directory: $($stackDirectory.FullName)"
        }
        $resolvedStackDirectory = Resolve-FinalItemPath -Path $stackDirectory.FullName
        if (-not (Test-PathContained -Child $resolvedStackDirectory -Parent $manifestRoot)) {
            throw "stack manifest directory escapes log root: $($stackDirectory.FullName) -> $resolvedStackDirectory"
        }

        $manifestPath = Join-Path $stackDirectory.FullName 'stack_manifest.json'
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            throw "malformed stack manifest is missing or not a file: $manifestPath"
        }
        $resolvedManifestPath = Resolve-FinalItemPath -Path $manifestPath
        if (-not (Test-PathContained -Child $resolvedManifestPath -Parent $resolvedStackDirectory)) {
            throw "stack manifest escapes its stack directory: $manifestPath -> $resolvedManifestPath"
        }

        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw -ErrorAction Stop |
                ConvertFrom-Json -ErrorAction Stop
            if ($manifest -isnot [pscustomobject] -or
                $manifest.schema_version -isnot [int] -or
                $manifest.schema_version -ne 2 -or
                $manifest.stack_id -isnot [string] -or
                -not $manifest.stack_id.Trim() -or
                $manifest.stack_id -ne $stackDirectory.Name -or
                $manifest.stop.clean -isnot [bool]) {
                throw 'manifest must be a schema v2 JSON object with a boolean stop.clean'
            }
        }
        catch {
            throw "malformed stack manifest: $manifestPath ($($_.Exception.Message))"
        }

        if ($manifest.stop.clean -ne $true) {
            throw "active stack manifest blocks log cleanup: $manifestPath"
        }
    }
}

try {
    $resolvedProjectRoot = Resolve-FinalItemPath -Path $ProjectRoot
    $logsCandidate = Join-Path $resolvedProjectRoot 'logs'
    if (-not (Test-Path -LiteralPath $logsCandidate)) {
        Write-Host "[clean-logs] logs directory is absent: $logsCandidate"
        exit 0
    }
    if (-not (Test-Path -LiteralPath $logsCandidate -PathType Container)) {
        throw "logs path is not a directory: $logsCandidate"
    }

    $resolvedLogRoot = Resolve-FinalItemPath -Path $logsCandidate
    $resolvedLogParent = Get-NormalizedPath -Path (Split-Path -Parent $resolvedLogRoot)
    if (-not (Test-PathEqual -Left $resolvedLogParent -Right $resolvedProjectRoot)) {
        throw "resolved logs directory is not a direct child of the project root: $logsCandidate -> $resolvedLogRoot"
    }

    $verifiedChildren = @()
    foreach ($child in @(Get-ChildItem -LiteralPath $logsCandidate -Force -ErrorAction Stop)) {
        $resolvedChild = Resolve-FinalItemPath -Path $child.FullName
        if (-not (Test-PathContained -Child $resolvedChild -Parent $resolvedLogRoot)) {
            throw "log child escapes resolved log root: $($child.FullName) -> $resolvedChild"
        }
        $verifiedChildren += [pscustomobject]@{
            Item = $child
            ResolvedPath = $resolvedChild
        }
    }

    Assert-CleanStackManifests -LogRoot $resolvedLogRoot -VerifiedChildren $verifiedChildren

    foreach ($verifiedChild in $verifiedChildren) {
        if ($Execute) {
            Write-Host "[REMOVE] $($verifiedChild.Item.FullName)"
            Remove-Item -LiteralPath $verifiedChild.Item.FullName -Recurse -Force -ErrorAction Stop
        }
        else {
            Write-Host "[DRY-RUN] remove $($verifiedChild.Item.FullName)"
        }
    }
    exit 0
}
catch {
    Write-Host "[FAIL] $($_.Exception.Message)"
    Write-Host '[FAIL] no log files were removed'
    exit 2
}
