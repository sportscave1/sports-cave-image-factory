"""Matched header browser comparison, same synthetic workflow and limits."""
import json
from time import perf_counter
from pathlib import Path
from tests.status_phase1_browser import run


if __name__ == '__main__':
    # The real route has loaded these during authentication/cache lookup before
    # response encoding; exclude test-only first-import cost from the browser pair.
    from companion_status_payload import payload, response
    from workspace_display_cache import user_scope
    baseline = Path('/tmp/header-baseline.html').read_text()
    result = dict(baseline=run(baseline), candidate=run(compact_status=True))
    assert result['candidate']['not_modified'] == 15
    assert result['baseline']['requests'] == result['candidate']['requests'] == 35
    assert [p['screenshot_sha256'] for p in result['baseline']['pages']] == [
        p['screenshot_sha256'] for p in result['candidate']['pages']]
    from tests.test_companion_status_payload import fixture
    source = fixture()
    result['populated_payload'] = []
    for _ in range(3):
        before = perf_counter(); original = json.dumps(source).encode(); baseline_ms = (perf_counter()-before)*1000
        before = perf_counter(); compact = json.dumps(payload(source), separators=(',', ':')).encode(); compact_ms = (perf_counter()-before)*1000
        result['populated_payload'].append(dict(baseline_bytes=len(original), candidate_bytes=len(compact),
            baseline_encode_ms=baseline_ms, candidate_project_and_encode_ms=compact_ms))
    print(json.dumps(result, indent=2))
