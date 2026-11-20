param(
    [string]$Python = 'python',
    [Parameter(Mandatory=$true)][string]$PGLiteModule
)
$ErrorActionPreference = 'Stop'
# Streamlit suites own global form/fragment state; isolate them by process.
$modules = @(
    'tests.test_shopify_sync',
    'tests.test_edition_recalculation_sales',
    'tests.test_edition_ledger_regressions',
    'tests.test_independent_edition_cursor',
    'tests.test_edition_order_recovery',
    'tests.test_edition_ops_table_editing'
)
Push-Location (Split-Path $PSScriptRoot -Parent)
$previousModule = $env:PGLITE_MODULE
try {
    foreach ($module in $modules) {
        & $Python -m unittest $module
        if ($LASTEXITCODE -ne 0) { throw "Failed suite: $module" }
    }
    $env:PGLITE_MODULE = $PGLiteModule
    & node tests/independent_cursor_postgres.mjs
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL allocation scenarios failed' }
    & $Python scripts/validate_render_topology.py
    if ($LASTEXITCODE -ne 0) { throw 'Render topology check failed' }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Diff whitespace check failed' }
} finally {
    $env:PGLITE_MODULE = $previousModule
    Pop-Location
}
