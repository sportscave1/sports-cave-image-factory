"""Real disposable SQL verifies heartbeat freshness and bounded read-only output."""
from unittest.mock import Mock

import auto_editions_header as header
from tests.test_auto_editions_discovery import database, store, pglite_database, PID


def test_empty_queue_fresh_stale_expired_and_revoked_hosts(store):
    queue, sql = store
    value = header.snapshot(queue.connect)
    assert value == dict(enabled=True, online=False, waiting=0, jobs=[])
    sql.execute("INSERT INTO auto_edition_preparation_hosts(token_hash,actor_id,session_version,last_seen_at) VALUES('synthetic','fixture','1',now())")
    assert header.snapshot(queue.connect)['online']
    sql.execute("UPDATE auto_edition_preparation_hosts SET last_seen_at=now()-interval '151 seconds'")
    assert not header.snapshot(queue.connect)['online']
    sql.execute("UPDATE auto_edition_preparation_hosts SET last_seen_at=now(),expires_at=now()-interval '1 second'")
    assert not header.snapshot(queue.connect)['online']
    sql.execute("UPDATE auto_edition_preparation_hosts SET expires_at=now()+interval '1 day',revoked_at=now()")
    assert not header.snapshot(queue.connect)['online']


def test_current_checkpoint_prioritised_bounded_and_no_mutation(store):
    queue, sql = store
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,priority) SELECT 'gid://shopify/Product/'||n,'id:fixture','Awaiting preparation',1 FROM generate_series(1,20) n")
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,reason,lease_until) VALUES(%s,'id:fixture','Preparing','Photoshop',now()+interval '1 minute')",(PID,))
    sql.execute('SELECT * FROM auto_edition_onboarding ORDER BY product_gid')
    before = sql.fetchall()
    value = header.snapshot(queue.connect)
    assert value['waiting'] == 20 and len(value['jobs']) == 10
    current = value['jobs'][0]
    assert current['id'] == PID and current['title'] == 'New Art'
    assert current['label'] == 'Photoshop' and current['state'] == 'running'
    assert current['percent'] == 0 and not current['estimated']
    sql.execute('SELECT * FROM auto_edition_onboarding ORDER BY product_gid')
    assert sql.fetchall() == before
    sql.execute("UPDATE auto_edition_onboarding SET reason='secret fixture credential',lease_until=now()-interval '1 second' WHERE product_gid=%s",(PID,))
    current = header.snapshot(queue.connect)['jobs'][0]
    assert current['label'] == 'Recovering · preparation lease expired'
    assert 'secret' not in str(current)


def test_completed_checkpoint_and_deferred_are_not_running(store):
    queue, sql = store
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status) VALUES(%s,'id:fixture','Cloud Ready')",(PID,))
    value = header.snapshot(queue.connect)
    assert value['jobs'][0]['label'] == 'Preparation saved'
    assert value['jobs'][0]['state'] == 'complete'
    sql.execute("UPDATE auto_edition_onboarding SET status='Awaiting preparation',priority=0")
    value = header.snapshot(queue.connect)
    assert value['jobs'][0]['state'] == 'pending' and value['waiting'] == 0
    sql.execute("UPDATE auto_edition_onboarding SET status='Blocked',reason='private database error'")
    value = header.snapshot(queue.connect)
    assert value['jobs'][0]['state'] == 'failed'
    assert 'private' not in str(value)


def test_failure_is_isolated_and_does_not_expose_error():
    value = header.snapshot(Mock(side_effect=RuntimeError('private database error')))
    assert value['unavailable'] and not value['online'] and value['jobs'] == []
    assert 'private' not in str(value)


def test_pause_replacement_and_cancellation_override_previous_success(store):
    queue, sql = store
    sql.execute("ALTER TABLE auto_edition_onboarding ADD COLUMN replacement jsonb, ADD COLUMN reset_cancellation jsonb")
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,replacement) VALUES(%s,'id:fixture','Cloud Ready','{\"stage\":\"Queued\"}')",(PID,))
    value = header.snapshot(queue.connect)
    assert value['waiting'] == 1 and value['jobs'][0]['state'] == 'waiting'
    sql.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,actor_id,event,detail) VALUES('auto-editions-worker-control','fixture','worker_paused','{\"paused\":true}')")
    assert not header.snapshot(queue.connect)['enabled']
    sql.execute("UPDATE auto_edition_onboarding SET replacement='{\"stage\":\"Discovering\"}'")
    assert header.snapshot(queue.connect)['jobs'][0]['label'] == 'Checking replacement source'
    sql.execute("UPDATE auto_edition_onboarding SET replacement='{\"stage\":\"Failed\"}'")
    assert header.snapshot(queue.connect)['jobs'][0]['state'] == 'failed'
    sql.execute("UPDATE auto_edition_onboarding SET reset_cancellation='{\"stage\":\"Cancelling\"}'")
    assert header.snapshot(queue.connect)['jobs'][0]['label'].startswith('Cancelling')


def test_active_repair_overrides_failed_preparation_and_counts_waiting(store):
    queue,sql=store
    sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,priority) VALUES(%s,'id:fixture','Blocked',10)",(PID,))
    sql.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,actor_id,event,detail) VALUES(%s,'fixture','edition_repair_request','{\"state\":\"Codex queued\"}')",(PID,))
    value=header.snapshot(queue.connect)
    assert value['waiting']==1 and value['jobs'][0]['state']=='waiting'
    assert value['jobs'][0]['label']=='Queued for Companion repair'
