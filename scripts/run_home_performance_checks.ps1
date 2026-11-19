# Synthetic tests only. Supply AUTO_EDITIONS_TEST_PGLITE and NODE_PATH for installed test dependencies.
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $env:AUTO_EDITIONS_TEST_PGLITE)) {
    throw 'Set AUTO_EDITIONS_TEST_PGLITE to the disposable test engine dist/index.js; database tests must not be skipped.'
}
$homeTests = @(
    'tests/test_home_status_performance.py', 'tests/test_home_fast_panels.py',
    'tests/test_home_saved_briefs_browser.py', 'tests/test_companion_header.py',
    'tests/test_companion_header_browser.py', 'tests/test_header_recovery_browser.py',
    'tests/test_top_bar.py', 'tests/test_home_shell_lazy.py',
    'tests/test_workspace_display_cache.py', 'tests/test_home_sports_morning_brief.py',
    'tests/test_daily_brief_reliability.py', 'tests/test_home_design_refresh.py',
    'tests/test_morning_design_queue.py', 'tests/test_product_upload_staff_queue.py',
    'tests/test_dashboard_home.py::SportsCaveDashboardStateTests::test_weekly_execution_summary_is_deterministic',
    'tests/test_dashboard_home.py::DashboardRenderContractTests::test_dashboard_uses_chatgpt_brief_and_weekly_work_without_restoring_legacy_events'
)
python -m pytest -q @homeTests --disable-warnings
if ($LASTEXITCODE -ne 0) { throw 'Home Python checks failed.' }
foreach ($homeScript in @('test_top_bar_requests.cjs', 'test_top_bar_navigation.cjs',
    'test_home_shell_component.cjs', 'test_home_design_queue_button.cjs',
    'test_email_connection_status.cjs', 'test_morning_design_companion.cjs')) {
    node (Join-Path 'tests' $homeScript)
    if ($LASTEXITCODE -ne 0) { throw "Home JavaScript check failed: $homeScript" }
}
