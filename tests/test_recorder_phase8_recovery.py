"""New recovery coverage only: never submit or repeat prior simulator workflows."""
import json
import pytest
from tests.fixtures.recorder_phase8_local import Scenario, CONVERSATION, ROOT

SAVED = ROOT/'evidence/recorder-reliability/phase8-local-followup-replay-20261029'
SOURCE = ROOT/'evidence/recorder-reliability/phase7-saved-replay-pass-20261029'


def snapshot(path):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in path.iterdir() if p.is_file()}


def test_recover_existing_saved_replay_read_only():
    before = snapshot(SAVED)
    scenario = Scenario(SOURCE, SAVED)
    result = scenario.recover_acknowledgement(CONVERSATION, scenario.digest)
    assert result['submissions'] == 1 and result['simulated'] is True
    assert snapshot(SAVED) == before


@pytest.mark.parametrize('damage', [
    'wrong_conversation', 'wrong_prompt', 'missing_attempt', 'missing_result',
    'corrupt_result', 'null_result', 'attempt_binding', 'result_binding',
    'duplicate', 'boolean_count', 'not_simulated', 'edition_change', 'production_job',
    'psd', 'wrong_draft', 'wrong_outcome', 'incomplete',
])
def test_recovery_refuses_without_writing(tmp_path, damage):
    for name in ('attempt.json', 'result.json'):
        (tmp_path/name).write_bytes((SAVED/name).read_bytes())
    conversation = CONVERSATION
    scenario = Scenario(SOURCE, tmp_path)
    digest = scenario.digest
    changes = {
        'result_binding': ('conversation', 'another-chat'),
        'duplicate': ('submissions', 2), 'boolean_count': ('submissions', True),
        'not_simulated': ('simulated', False), 'edition_change': ('edition_changes', 1),
        'production_job': ('production_jobs', 1), 'psd': ('psd_attached', True),
        'wrong_draft': ('draft_id', 'other'), 'wrong_outcome': ('business_outcome', 'real'),
        'incomplete': ('state', 'pending'),
    }
    if damage == 'wrong_conversation':
        conversation = 'another-chat'
    elif damage == 'wrong_prompt':
        digest = '0'*64
    elif damage.startswith('missing_'):
        (tmp_path/(damage.removeprefix('missing_')+'.json')).unlink()
    elif damage in ('corrupt_result', 'null_result'):
        (tmp_path/'result.json').write_text('{' if damage == 'corrupt_result' else 'null')
    else:
        path = tmp_path/('attempt.json' if damage == 'attempt_binding' else 'result.json')
        data = json.loads(path.read_text())
        key, value = ('prompt_sha256', 'wrong') if damage == 'attempt_binding' else changes[damage]
        data[key] = value
        path.write_text(json.dumps(data))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        scenario.recover_acknowledgement(conversation, digest)
    assert snapshot(tmp_path) == before
