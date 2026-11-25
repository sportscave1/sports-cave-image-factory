"""No mailbox connection: truthful owner-facing certificate outcomes."""
import pytest
from inbox_companion_ui import certificate_outcome


def test_accepted_reply_does_not_repeat_old_queue_reason():
    label, message = certificate_outcome('accepted', 'Certificate access reply queued.')
    assert label == '✓ Companion sent'
    assert 'queued' not in message.lower()


@pytest.mark.parametrize('status', ['queued', 'in_progress', 'unknown', 'rejected',
                                    'review', 'answered', 'ignored', '', 'unexpected'])
def test_only_confirmed_automatic_sends_receive_a_sent_tick(status):
    label, _ = certificate_outcome(status, 'Certificate access reply queued.')
    assert '✓' not in label
    assert 'Companion sent' not in label


def test_uncertain_delivery_prevents_manual_resend_hint():
    label, message = certificate_outcome('unknown')
    assert label == 'Checking reply'
    assert 'Do not resend' in message


def test_review_keeps_actionable_reason():
    assert certificate_outcome('review', 'A saved draft already exists.')[1] == 'A saved draft already exists.'
