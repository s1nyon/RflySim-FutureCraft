$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\PX4PSP\Python38\python.exe'
$catalog = Join-Path $projectRoot 'config\calibration\official_asset_candidates_v1.json'
$catalogModule = Join-Path $projectRoot 'scripts\calibration\asset_catalog.py'
$geometryModule = Join-Path $projectRoot 'scripts\calibration\calibration_geometry.py'
$artifactModule = Join-Path $projectRoot 'scripts\calibration\calibration_artifacts.py'
$loaderModule = Join-Path $projectRoot 'scripts\calibration\ue_asset_loader.py'
$metadataModule = Join-Path $projectRoot 'scripts\calibration\object_metadata.py'
$cli = Join-Path $projectRoot 'scripts\calibration\calibration_cli.py'

function Invoke-Checked {
    param([Parameter(Mandatory = $true)][string]$FilePath,
          [Parameter(Mandatory = $true)][string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

Push-Location $projectRoot
try {
    Invoke-Checked $python @('tests\asset_calibration_catalog_check.py', '--module', $catalogModule, '--catalog', $catalog)
    Invoke-Checked $python @('tests\asset_calibration_geometry_check.py', '--catalog-module', $catalogModule, '--geometry-module', $geometryModule, '--catalog', $catalog)
    Invoke-Checked $python @('tests\asset_calibration_artifacts_check.py', '--catalog-module', $catalogModule, '--geometry-module', $geometryModule, '--artifact-module', $artifactModule, '--catalog', $catalog)
    Invoke-Checked $python @('tests\asset_calibration_ue_loader_check.py', '--catalog-module', $catalogModule, '--geometry-module', $geometryModule, '--loader-module', $loaderModule, '--catalog', $catalog)
    Invoke-Checked $python @('tests\asset_calibration_metadata_check.py', '--catalog-module', $catalogModule, '--geometry-module', $geometryModule, '--metadata-module', $metadataModule, '--catalog', $catalog)
    Invoke-Checked $python @('tests\asset_calibration_cli_check.py', '--cli', $cli, '--catalog', $catalog)
    Invoke-Checked $python @('tests\asset_showcase_geometry_check.py', '--catalog-module', $catalogModule, '--showcase-module', 'scripts\calibration\showcase_geometry.py', '--catalog', $catalog, '--showcase', 'config\calibration\official_asset_showcase_v1.json')
    Invoke-Checked $python @('tests\asset_showcase_artifacts_check.py', '--root', '.')
    Invoke-Checked $python @('tests\asset_showcase_cli_check.py', '--cli', $cli, '--catalog', $catalog, '--showcase', 'config\calibration\official_asset_showcase_v1.json')
    Invoke-Checked $python @($cli, 'load', '--catalog', $catalog)
    Invoke-Checked $python @($cli, 'record', '--catalog', $catalog, '--output', 'logs\calibration\offline-dry-run')
    Invoke-Checked $python @($cli, 'remove', '--catalog', $catalog)
    Invoke-Checked $python @($cli, 'showcase-load', '--catalog', $catalog, '--showcase', 'config\calibration\official_asset_showcase_v1.json')
    Invoke-Checked $python @($cli, 'showcase-remove', '--catalog', $catalog, '--showcase', 'config\calibration\official_asset_showcase_v1.json')
    Invoke-Checked 'git.exe' @('diff', '--check')
    Write-Output '[PASS] Official asset calibration offline validation PASS'
}
finally {
    Pop-Location
}
