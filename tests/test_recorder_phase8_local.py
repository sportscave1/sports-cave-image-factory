import json
import pytest
from tests.fixtures.recorder_phase8_local import Scenario, CONVERSATION, ROOT

EVIDENCE = ROOT/'evidence/recorder-reliability/phase7-saved-replay-pass-20261029'


@pytest.mark.parametrize('change', [dict(conversation='another-chat'), dict(ready=False), dict(prompt='truncated')])
def test_followup_fails_before_attempt(tmp_path, change):
    scenario = Scenario(EVIDENCE, tmp_path)
    request = dict(conversation=CONVERSATION, ready=True, prompt=scenario.prompt)
    request.update(change)
    with pytest.raises(ValueError):
        scenario.submit(request)
    assert not list(tmp_path.iterdir())


def test_one_submission_and_restart_never_repeat(tmp_path):
    scenario = Scenario(EVIDENCE, tmp_path)
    request = dict(conversation=CONVERSATION, ready=True, prompt=scenario.prompt)
    result = scenario.submit(request)
    assert result['submissions'] == 1 and result['simulated']
    assert result['edition_changes'] == result['production_jobs'] == 0
    assert result['psd_attached'] is False
    before = (tmp_path/'result.json').read_bytes()
    with pytest.raises(FileExistsError):
        Scenario(EVIDENCE, tmp_path).submit(request)
    assert (tmp_path/'result.json').read_bytes() == before


def test_unknown_outcome_blocks_resend(tmp_path):
    scenario = Scenario(EVIDENCE, tmp_path)
    (tmp_path/'attempt.json').write_text(json.dumps(dict(state='attempted')))
    with pytest.raises(FileExistsError):
        scenario.submit(dict(conversation=CONVERSATION, ready=True, prompt=scenario.prompt))
    assert not (tmp_path/'result.json').exists()
