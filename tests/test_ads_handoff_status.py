"""Offline state-machine checks: a missing browser receipt is not a failed ad."""
import pytest
import design_publish_ad as ads

CHAT = ads.PROJECT.replace('/project', '/c/00000000-0000-0000-0000-000000000001')

@pytest.fixture
def checkpoint(monkeypatch):
    monkeypatch.setattr(ads, 'write', lambda *args: None)
    monkeypatch.setattr(ads, '_post_request', lambda value: None)
    monkeypatch.setattr(ads.time, 'time', lambda: 10000)
    return dict(upload='00000000-0000-0000-0000-000000000002', stage='opening', prompt='original brief')

def step(value, event, age=20):
    return ads._step('fixture', value, {'stage': 6}, event, age)

def test_uncertain_handoff_keeps_checkpoint_then_recovers_same_chat(checkpoint):
    value = checkpoint
    assert step(value, {'state': 'uncertain'})['stage'] == 'opening'
    assert value['prompt'] == 'original brief'
    assert 'Confirming' in ads.public(value)['label']
    result = step(value, {'state': 'submitted', 'chat_url': CHAT, 'generating': True, 'activity': '1'})
    assert result['stage'] == 'generating' and result['chat_url'] == CHAT
    assert 'prompt' not in value and not value.get('handoff_pending')
    assert 'thinking / generating' in ads.public(value)['label']

def test_handoff_timeout_cannot_be_extended_by_polling(checkpoint):
    step(checkpoint, {'state': 'uncertain'}, age=3500)
    assert checkpoint['handoff_started_at'] == 6500
    checkpoint['handoff_started_at'] = 6000
    with pytest.raises(ValueError, match='do not resend'):
        step(checkpoint, {'state': 'uncertain'}, age=1)

def test_active_generation_survives_old_checkpoint_but_idle_does_not(checkpoint):
    checkpoint.update(stage='generating', chat_url=CHAT)
    step(checkpoint, {'state': 'submitted', 'chat_url': CHAT, 'generating': True, 'activity': '1'}, age=9000)
    assert checkpoint['last_chat_activity_at'] == 10000
    checkpoint.update(last_chat_activity_at=1, chat_generating=False)
    with pytest.raises(ValueError, match='did not arrive'):
        step(checkpoint, {'state': 'submitted', 'chat_url': CHAT, 'generating': False, 'activity': '1'}, age=1)

def test_unrelated_chat_cannot_refresh_activity(checkpoint):
    checkpoint.update(stage='generating', chat_url=CHAT, last_chat_activity_at=1)
    with pytest.raises(ValueError, match='did not arrive'):
        step(checkpoint, {'state': 'submitted', 'chat_url': CHAT[:-1]+'9', 'generating': True}, age=9000)
    assert checkpoint['chat_url'] == CHAT

def test_empty_heartbeat_cannot_extend_legacy_idle_job(checkpoint):
    checkpoint.update(stage='generating', chat_url=CHAT)
    with pytest.raises(ValueError, match='did not arrive'):
        step(checkpoint, {'state': 'submitted', 'chat_url': CHAT, 'generating': False}, age=9000)
    assert checkpoint['last_chat_activity_at'] == 1000

def test_real_blocker_retains_chat_for_review(checkpoint):
    with pytest.raises(ValueError, match='safety rejection'):
        step(checkpoint, {'state': 'blocked', 'chat_url': CHAT, 'reason': 'Two covers incomplete: safety rejection'})
    assert checkpoint['chat_url'] == CHAT

def test_stale_uncertain_does_not_fail_confirmed_generation(checkpoint):
    checkpoint.update(stage='generating', chat_url=CHAT)
    assert step(checkpoint, {'state': 'uncertain'})['stage'] == 'generating'

def test_thinking_label_expires_when_browser_observation_stops(checkpoint):
    checkpoint.update(stage='generating', chat_generating=True, chat_observed_at=9000)
    assert 'thinking' not in ads.public(checkpoint)['label']


def test_live_generation_hides_stale_transfer_warning_without_erasing_it(checkpoint):
    checkpoint.update(stage='generating', chat_generating=True, chat_observed_at=10000,
                      detail='Original queued prompt is not loaded. Press Play to resume this saved chat.')
    assert ads.public(checkpoint)['detail'] == 'ChatGPT is still generating; waiting for finished attachments'
    assert 'Press Play' in checkpoint['detail']
    checkpoint['chat_generating'] = False
    assert 'Press Play' in ads.public(checkpoint)['detail']
    checkpoint.update(stage='failed', detail='Image provider rejected the hallway cover')
    assert ads.public(checkpoint)['detail'] == 'Image provider rejected the hallway cover'
