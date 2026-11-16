"""Generation acknowledgement must follow the current, applied application result."""
import pytest
from product_upload_generation_status import attempt, status, markup, recover_review_attempt


def test_ready_requires_matching_job_applied_result_and_current_context():
    context = ("design", "Example", "Cricket", "source-a")
    value = attempt(*context, job="job-a")
    result = dict(_product_upload_intake="design", _product_upload_source_hash="source-a",
                  product_name="Example", sport_category="Cricket")
    assert status(None, None, None, result, *context) == ("ready", "0" * 32)
    assert status(None, None, None, None, *context) == ("idle", "0" * 32)
    def state(job, applied=None, output=None, ctx=context):
        return status(value, job, applied, output, *ctx)[0]
    assert state(dict(token="job-a", state="Running")) == "working"
    ready = dict(token="job-a", state="Ready")
    assert state(ready, output=result) == "working"
    assert state(ready, "job-a", result) == "ready"
    assert state(ready, "old-job", result) == "working"
    assert state(dict(token="old-job", state="Ready"), "old-job", result) == "changed"
    assert state(dict(token="job-a", state="Failed"), "job-a", result) == "failed"
    assert state(ready, "job-a", result, ("design", "Changed", "Cricket", "source-a")) == "changed"
    assert state(ready, "job-a", {**result, "_product_upload_source_hash":"old"}) == "working"


def test_reused_result_has_a_fresh_acknowledgement_and_cannot_acknowledge_stale_output():
    context = ("design", "Example", "Cricket", "source-a")
    first, second = attempt(*context, reused=True), attempt(*context, reused=True)
    assert first["receipt"] != second["receipt"]
    result = dict(_product_upload_intake="design", _product_upload_source_hash="source-a",
                  product_name="Example", sport_category="Cricket")
    assert status(second, None, None, result, *context)[0] == "ready"
    assert status(second, None, None, None, *context)[0] == "changed"
    html = markup("ready", second["receipt"])
    assert 'role="status"' in html and '>Mockups ready<' in html
    assert 'source-a' not in html and 'Example' not in html
    with pytest.raises(ValueError):
        markup("ready", '<script>')


def test_review_recovers_the_exact_prepared_result_without_a_browser_acknowledgement():
    row = {'id': 'design', 'data': {'source': {'content_hash': 'source-a', 'rev': 'revision-a'},
                                   'design_review': {'decision': 'approved'}}}
    choice = {'id': 'folder-a', 'sport': 'Cricket'}
    result = dict(_product_upload_intake='design', _product_upload_source_hash='source-a',
                  product_name='Example', sport_category='Cricket', run_dir='retained-run')
    value = recover_review_attempt(row, result, choice, 'Example')
    assert value['receipt'] == recover_review_attempt(row, result, choice, 'Example')['receipt']
    assert status(value, None, None, result, 'design', 'Example', 'Cricket', 'source-a')[0] == 'ready'
    assert recover_review_attempt(row, result, choice, 'Renamed') is None
    assert recover_review_attempt(row, {**result, '_product_upload_source_hash': 'other'}, choice, 'Example') is None
    row['data']['design_review']['decision'] = 'changes'
    assert recover_review_attempt(row, result, choice, 'Example') is None
