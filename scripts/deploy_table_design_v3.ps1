# Manual publishing by default; -VerifyOnly validates the exact package without a commit or push.
[CmdletBinding()]
param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$sourceRoot = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $sourceRoot 'docs/table-v3-release'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $bundle 'manifest.json') | ConvertFrom-Json
if (-not ($manifest.PSObject.Properties.Name -contains 'schema_version') -or $manifest.schema_version -ne 2) {
    throw 'Obsolete Table Design release bundle. The old patch is not accepted by this script.'
}
if ($manifest.status -ne 'verified' -and -not $VerifyOnly) { throw 'Release bundle has not passed final verification.' }
$patchPath = Join-Path $bundle 'changes.patch'
function Assert-Hash($path, $expected) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() -ne $expected) {
        throw "Verified release file changed: $path"
    }
}
Assert-Hash $PSCommandPath $manifest.deployment_script_sha256
Assert-Hash $patchPath $manifest.patch_sha256
foreach ($item in $manifest.assets) { Assert-Hash (Join-Path $sourceRoot $item.path) $item.sha256 }
$python = Join-Path $sourceRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'The verified repository Python environment is missing.' }
function Invoke-CheckedGit {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "Git stopped (exit $LASTEXITCODE). No force push or conflict override is permitted." }
}
$releaseRoot = Join-Path ([IO.Path]::GetTempPath()) ('sports-cave-table-v3-' + [guid]::NewGuid().ToString('N'))
$oldPythonPath = $env:PYTHONPATH
$oldNodePath = $env:NODE_PATH
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
Push-Location -LiteralPath $sourceRoot
try {
    $remote = (& git remote get-url origin)
    if ($LASTEXITCODE -ne 0 -or $remote -ne $manifest.remote) { throw 'Origin does not match the verified release repository.' }
    Invoke-CheckedGit clone --single-branch --branch main -- $remote $releaseRoot
    Set-Location -LiteralPath $releaseRoot
    $base = (& git rev-parse HEAD)
    if ($LASTEXITCODE -ne 0 -or $base -ne $manifest.base_revision) {
        throw "GitHub main changed since verification. Expected $($manifest.base_revision); found $base. Reconciliation is required; no changes were pushed."
    }
    Invoke-CheckedGit checkout -b codex/table-design-v3
    Invoke-CheckedGit apply --check --index -- $patchPath
    Invoke-CheckedGit apply --index -- $patchPath
    foreach ($item in $manifest.assets) {
        $target = Join-Path $releaseRoot $item.path
        [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceRoot $item.path) -Destination $target
        Invoke-CheckedGit add -- $item.path
    }
    $actual = @(& git diff --cached --name-only) | Sort-Object
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the release index.' }
    if (Compare-Object $actual (@($manifest.files) | Sort-Object)) { throw 'Unexpected release file set.' }
    foreach ($item in $manifest.outputs) { Assert-Hash (Join-Path $releaseRoot $item.path) $item.sha256 }
    Invoke-CheckedGit diff --cached --check
    $env:PYTHONPATH = $releaseRoot
    if (-not $env:NODE_PATH) {
        $bundledNode = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
        if (Test-Path -LiteralPath $bundledNode) { $env:NODE_PATH = $bundledNode }
    }
    $env:TEMP = Join-Path $releaseRoot 'tmp'
    $env:TMP = $env:TEMP
    [IO.Directory]::CreateDirectory($env:TEMP) | Out-Null
    & $python scripts/verify_table_design_v3_release.py --dependency-root $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw 'Release validation failed. Nothing has been committed or pushed.' }
    # Tests can generate evidence files. Commit only the frozen, verified index.
    $tree = (& git write-tree)
    if ($LASTEXITCODE -ne 0 -or $tree -ne $manifest.expected_tree) { throw 'Frozen release index changed during verification.' }
    Invoke-CheckedGit fetch origin main
    $current = (& git rev-parse origin/main)
    if ($LASTEXITCODE -ne 0 -or $current -ne $manifest.base_revision) { throw 'GitHub main advanced during validation. Nothing has been committed or pushed.' }
    if ($VerifyOnly) {
        Write-Host "VERIFY ONLY PASSED. No commit, push or deployment. Checkout: $releaseRoot"
    } else {
        Invoke-CheckedGit commit -m 'Unify Sports Cave OS table presentation'
        Invoke-CheckedGit push origin HEAD:main
        Write-Host "Verified Table Design V3 pushed to main; existing Render auto-deployment can run. Checkout: $releaseRoot"
    }
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:NODE_PATH = $oldNodePath
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    Pop-Location
    Write-Host "Original working files preserved. Release checkout retained: $releaseRoot"
}
