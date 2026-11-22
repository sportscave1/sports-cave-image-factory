"""Disposable PostgreSQL: short poll deadlines, rollback, and heartbeat pacing."""
import pytest
from unittest.mock import MagicMock, Mock
from test_auto_editions_jobs import database
from companion_poll_transaction import connection, authenticate_and_touch


def test_overlapping_polls_are_rejected_before_opening_another_database_connection():
    factory = MagicMock()
    with connection(factory), connection(factory):
        with pytest.raises(RuntimeError, match='retry the saved event'):
            with connection(factory):
                pytest.fail('An overloaded poll must not be admitted')
        assert factory.call_count == 2
    with connection(factory):
        pass
    assert factory.call_count == 3


def test_failed_connection_releases_poll_admission_slot():
    broken = Mock(side_effect=OSError('synthetic connection unavailable'))
    for _ in range(3):
        with pytest.raises(OSError):
            with connection(broken):
                pass
    assert broken.call_count == 3


def test_deadlines_are_transaction_local_and_failed_poll_rolls_back(database):
    jobs, cur = database
    cur.execute('CREATE TABLE poll_receipts(id integer)')
    with pytest.raises(ValueError):
        with connection(jobs.connect) as conn, conn.cursor() as poll:
            poll.execute("SELECT current_setting('lock_timeout') AS lock, current_setting('statement_timeout') AS statement")
            assert poll.fetchone() == {'lock': '750ms', 'statement': '8s'}
            poll.execute('INSERT INTO poll_receipts VALUES(1)')
            raise ValueError('retry the retained event')
    cur.execute('SELECT count(*)::integer AS n FROM poll_receipts')
    assert cur.fetchone()['n'] == 0
    cur.execute("SELECT current_setting('lock_timeout') AS lock")
    assert cur.fetchone()['lock'] == '0'


def test_heartbeat_paces_writes_and_always_checks_current_pairing(database):
    jobs, cur = database
    cur.execute('CREATE TABLE product_upload_desktop(singleton boolean PRIMARY KEY,token_hash text,actor_id text,seen_at timestamptz)')
    cur.execute("INSERT INTO product_upload_desktop VALUES(true,'fixture-hash','fixture-actor',NULL)")
    with connection(jobs.connect) as conn, conn.cursor() as poll:
        assert authenticate_and_touch(poll, 'wrong-hash') is None
        poll.execute('SELECT seen_at FROM product_upload_desktop')
        assert poll.fetchone()['seen_at'] is None
        assert authenticate_and_touch(poll, 'fixture-hash')['actor_id'] == 'fixture-actor'
    cur.execute('SELECT seen_at::text AS first FROM product_upload_desktop')
    first = cur.fetchone()['first']
    with connection(jobs.connect) as conn, conn.cursor() as poll:
        assert authenticate_and_touch(poll, 'fixture-hash')['actor_id'] == 'fixture-actor'
    cur.execute('SELECT seen_at::text AS first FROM product_upload_desktop')
    assert cur.fetchone()['first'] == first
    cur.execute("UPDATE product_upload_desktop SET seen_at=now()-interval '21 seconds'")
    with connection(jobs.connect) as conn, conn.cursor() as poll:
        assert authenticate_and_touch(poll, 'fixture-hash')['actor_id'] == 'fixture-actor'
    cur.execute('SELECT seen_at>now()-interval \'5 seconds\' AS fresh FROM product_upload_desktop')
    assert cur.fetchone()['fresh']
    cur.execute("UPDATE product_upload_desktop SET token_hash='new-fixture-hash'")
    with connection(jobs.connect) as conn, conn.cursor() as poll:
        assert authenticate_and_touch(poll, 'fixture-hash') is None
