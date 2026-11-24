from copy import deepcopy
from scripts.check_os_performance import check


def evidence():
    sample = dict(cold=dict(assets=[dict(encodedBytes=802542, transferBytes=806442)],
        usableMs=900, assetHeaders={"/static/js/index.hash.js":dict(encoding="br")}),
        reopened=dict(assets=[dict(transferBytes=0)]), errors=[], external_requests=[])
    startup = dict(normal=[deepcopy(sample) for _ in range(3)], slow=[deepcopy(sample)], restarts=[{}])
    pages = dict(results=[
        dict(mode="after", route="Home", ready_ms=450, full_app_runs_for_navigation=1),
        dict(mode="after", route="Orders", simulated_read_seconds=1.4, ready_ms=1900,
             full_app_runs_for_navigation=1, search_ms=1600, search_full_app_reruns=0,
             previous_rows_visible_during_search=True)])
    return startup, pages


def test_accepts_measured_shape_and_rejects_missing_coverage():
    startup, pages = evidence()
    assert check(startup, pages) == []
    assert check({}, {})  # An empty artifact cannot falsely pass.


def test_rejects_transfer_browser_and_render_regressions():
    startup, pages = evidence()
    for sample in startup["normal"]:
        sample["cold"]["assets"][0]["encodedBytes"] = 1000000
        sample["reopened"]["assets"][0]["transferBytes"] = 100
        sample["errors"] = ["script failure"]
    pages["results"][1].update(full_app_runs_for_navigation=2, search_full_app_reruns=1,
                               previous_rows_visible_during_search=False)
    failures = check(startup, pages)
    assert "median frontend encoding <=850000 bytes" in failures
    assert "zero cached bundle transfer" in failures
    assert "no browser or external-network errors" in failures
    assert "no completion full-app rerun" in failures
    assert "no search full-app rerun" in failures
    assert "retain rows during slow search" in failures
