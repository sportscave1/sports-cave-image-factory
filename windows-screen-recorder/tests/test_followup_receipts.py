"""Offline contract tests only. No browser/store effects or prior replay repeats."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
import pytest
from desktop_recorder.contract import Invalid
from desktop_recorder.followup_receipts import FollowupJournal, verify_prepared


@pytest.fixture
def binding():
    return dict(browser='edge', profile='test-profile', extension_instance='test-extension',
        conversation_url='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0',
        source_url='http://127.0.0.1:18963/?page=product_uploads',
        mapping_url='http://127.0.0.1:18963/?page=edition_ops', store_id='offline-test',
        product_id='offline-product', save_token='offline-save',
        prompt_sha256=hashlib.sha256(b'complete\nprompt').hexdigest(),
        files_sha256='a'*64, recording_revision='b'*64, coverage='simulated')


def ack(binding):
    return dict({k: binding[k] for k in ('conversation_url', 'prompt_sha256', 'profile',
                'extension_instance', 'coverage')}, message_id='offline-message', matching_user_messages=1)


@pytest.mark.parametrize('key', ['browser', 'profile', 'extension_instance', 'conversation_url',
    'source_url', 'mapping_url', 'store_id', 'product_id', 'save_token', 'prompt_sha256',
    'files_sha256', 'recording_revision', 'coverage'])
def test_changed_observation_refused(binding, key):
    with pytest.raises(Invalid):
        verify_prepared(binding, dict(binding, **{key: 'changed'}), 'complete\nprompt')


@pytest.mark.parametrize('text', ['truncated', '', None, 'stale clipboard'])
def test_incomplete_or_stale_prompt_refused(binding, text):
    with pytest.raises(Invalid):
        verify_prepared(binding, binding, text)


def test_normalized_full_prompt(binding):
    verify_prepared(binding, binding, 'complete\r\nprompt')


def test_restart_unknown_outcome_cannot_resend(tmp_path, binding):
    path = tmp_path/'followup.sqlite'
    FollowupJournal(path).reserve(binding)
    restarted = FollowupJournal(path)
    with pytest.raises(Invalid, match='do not resend'):
        restarted.recover(binding)
    with pytest.raises(Invalid, match='already attempted'):
        restarted.reserve(binding)
    # Moving conversation or changing prompt does not create another attempt.
    for field, value in [('profile', 'other'), ('prompt_sha256', 'c'*64),
                         ('conversation_url', binding['conversation_url'].replace('6ae2d62d', '7ae2d62d'))]:
        with pytest.raises(Invalid):
            restarted.reserve(dict(binding, **{field: value}))


def test_recovery_readonly_and_ack_idempotent(tmp_path, binding):
    path = tmp_path/'followup.sqlite'
    journal = FollowupJournal(path)
    journal.reserve(binding)
    journal.acknowledge(binding, ack(binding))
    journal.acknowledge(binding, ack(binding))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    assert journal.recover(binding) == ack(binding)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    with pytest.raises(Invalid):
        journal.acknowledge(binding, dict(ack(binding), message_id='second-message'))


@pytest.mark.parametrize('key,value', [('conversation_url', 'other'), ('prompt_sha256', 'c'*64),
    ('profile', 'other'), ('extension_instance', 'other'), ('coverage', 'isolated-nonproduction'),
    ('matching_user_messages', 0), ('matching_user_messages', 2), ('matching_user_messages', True),
    ('message_id', ''), ('message_id', None)])
def test_wrong_or_ambiguous_ack_refused(tmp_path, binding, key, value):
    journal = FollowupJournal(tmp_path/'followup.sqlite')
    journal.reserve(binding)
    with pytest.raises(Invalid):
        journal.acknowledge(binding, dict(ack(binding), **{key: value}))
    with pytest.raises(Invalid):
        journal.recover(binding)


def test_no_ack_without_attempt(tmp_path, binding):
    with pytest.raises(Invalid):
        FollowupJournal(tmp_path/'followup.sqlite').acknowledge(binding, ack(binding))


def test_concurrent_attempts_have_one_winner(tmp_path, binding):
    journal = FollowupJournal(tmp_path/'followup.sqlite')
    def reserve(_):
        try:
            journal.reserve(binding)
            return True
        except Invalid:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(8))) == 1


def test_production_or_unverified_refused(tmp_path, binding):
    journal = FollowupJournal(tmp_path/'followup.sqlite')
    for coverage in ('production', 'real', 'pending', 'unknown'):
        with pytest.raises(Invalid):
            journal.reserve(dict(binding, coverage=coverage))


@pytest.mark.parametrize('damaged', ['{', 'null', '{}', json.dumps({'matching_user_messages': 2})])
def test_corrupt_acknowledgement_refused_readonly(tmp_path, binding, damaged):
    path = tmp_path/'followup.sqlite'
    journal = FollowupJournal(path)
    journal.reserve(binding)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE followups SET acknowledgement=?', (damaged,))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    with pytest.raises(Invalid):
        journal.recover(binding)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
