"""Durable SEO Companion work in the existing hosted worker; no storefront writes."""
from datetime import datetime, timezone
import hashlib
import json
import logging
import uuid

import os_accounts
from seo_companion_audit import public_url

SETTINGS = 'seo_companion_settings'
PREFIX = 'seo_companion_job:'
REVIEW_PREFIX = 'seo_companion_review:'
LOG = logging.getLogger(__name__)


def connect():
    from supabase_backend import connect as database
    return database()


def now():
    return datetime.now(timezone.utc).isoformat()


def permitted(user):
    return (os_accounts.is_reporting_owner(user) and os_accounts.can_access_page(user, 'seo')
            and os_accounts.can_access_page(user, 'Upload Companion'))


def _setting(cur, key):
    cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
    row = cur.fetchone()
    return row['value'] if row else {}


def _put(cur, key, value):
    cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()''', (key, json.dumps(value)))


def enqueue_daily(cur, edition):
    """Called in the publication transaction; first accepted edition/date wins."""
    settings = _setting(cur, SETTINGS)
    if not settings.get('enabled'):
        return None
    targets = list(dict.fromkeys(public_url(row['url']) for row in edition.get('opportunities', [])))[:3]
    payload = {'id': edition['date'], 'date': edition['date'], 'stage': 'queued',
               'owner': settings['owner'], 'session_version': settings['session_version'],
               'targets': targets, 'instruction': edition['next_action'], 'report_summary': edition['summary'],
               'attempts': 0, 'created_at': now(), 'progress': {}, 'result': None,
               'report_hash': hashlib.sha256(json.dumps(edition, sort_keys=True).encode()).hexdigest()}
    cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
                   ON CONFLICT DO NOTHING''', (PREFIX + edition['date'], json.dumps(payload)))
    return _setting(cur, PREFIX + edition['date'])


def configure(user, enabled):
    if not permitted(user):
        raise PermissionError('The reporting owner with SEO and Companion access must control daily SEO work.')
    from sports_sales_calendar import sydney_date
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (SETTINGS,))
        settings = {'enabled': bool(enabled), 'owner': user['id'],
                    'session_version': str(user.get('session_version') or 1), 'updated_at': now()}
        _put(cur, SETTINGS, settings)
        report = _setting(cur, 'home_seo_daily_report')
        queued = enqueue_daily(cur, report) if report.get('date') == str(sydney_date()) and enabled else None
    return queued


def snapshot(limit=20):
    with connect() as conn, conn.cursor() as cur:
        settings = _setting(cur, SETTINGS)
        cur.execute('SELECT value FROM app_settings WHERE key LIKE %s ORDER BY key DESC LIMIT %s',
                    (PREFIX + '%', min(max(int(limit), 1), 30)))
        jobs = [row['value'] for row in cur.fetchall()]
        cur.execute('SELECT value FROM app_settings WHERE key LIKE %s ORDER BY updated_at DESC LIMIT 500',
                    (REVIEW_PREFIX + '%',))
        reviews = [row['value'] for row in cur.fetchall()]
    return {'settings': settings, 'jobs': jobs, 'reviews': reviews}


def claim():
    from sports_sales_calendar import sydney_date
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (SETTINGS,))
        settings = _setting(cur, SETTINGS)
        if not settings.get('enabled'):
            return None
        report = _setting(cur, 'home_seo_daily_report')
        if report.get('date') == str(sydney_date()):
            enqueue_daily(cur, report)
        cur.execute('''SELECT key,value FROM app_settings WHERE key LIKE %s
            AND value->>'date'=%s AND (value->>'attempts')::integer < 3 AND (
              value->>'stage'='queued' OR
              (value->>'stage'='retrying' AND updated_at < now()-interval '2 minutes') OR
              (value->>'stage'='running' AND updated_at < now()-interval '15 minutes'))
            ORDER BY key LIMIT 1 FOR UPDATE SKIP LOCKED''', (PREFIX + '%', str(sydney_date())))
        row = cur.fetchone()
        if not row:
            return None
        job = row['value']
        job.update(stage='running', lease=str(uuid.uuid4()), started_at=now(), attempts=job['attempts'] + 1)
        _put(cur, row['key'], job)
        return job


def _checkpoint(job, *, progress=None, result=None, error=None):
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (PREFIX + job['id'],))
        row = cur.fetchone()
        if not row or row['value'].get('lease') != job['lease']:
            raise InterruptedError('Audit lease has changed; stale output was not saved.')
        current = row['value']
        if progress is not None:
            current['progress'] = progress
        if result is not None:
            current.update(result=result, finished_at=now(), stage='ready_for_review')
        if error is not None:
            current.update(error=error, stage='retrying' if current['attempts'] < 3 else 'needs_attention')
        _put(cur, PREFIX + job['id'], current)


def process_one(stop=None):
    job = claim()
    if not job:
        return False
    try:
        user = os_accounts.DEFAULT_STORE.get_user(job['owner'])
        if not permitted(user) or str(user.get('session_version') or 1) != job['session_version']:
            raise PermissionError('Companion owner access changed; renew daily SEO permission.')
        import requests
        from seo_companion_audit import PublicCrawler, audit, MAX_REQUESTS
        with requests.Session() as session:
            crawler = PublicCrawler(session, request_limit=MAX_REQUESTS, timeout=10, max_attempts=1)
            result = audit(job, crawler=crawler, progress=lambda value: _checkpoint(job, progress=value),
                           stopped=lambda: bool(stop and stop.is_set()))
        _checkpoint(job, result=result)
        LOG.info('seo_companion_review_ready date=%s pages=%s links=%s gaps=%s', job['date'],
                 len(result['pages']), len(result['links']), len(result['gaps']))
    except Exception as error:
        # Never leak response bodies, connection details or credentials into results.
        message = ('Companion permission changed. Re-enable daily SEO after access is restored.'
                   if isinstance(error, PermissionError) else 'Audit interrupted or unavailable (' + type(error).__name__ + ').')
        try:
            _checkpoint(job, error=message)
        except InterruptedError:
            pass
        LOG.warning('seo_companion_audit_incomplete date=%s error_type=%s', job['date'], type(error).__name__)
    return True


def review(user, job_id, proposal_id, decision, expected_revision):
    if not permitted(user):
        raise PermissionError('Reporting owner and SEO/Companion access required.')
    if decision not in ('Approved for implementation', 'Changes requested', 'Dismissed'):
        raise ValueError('Choose a review decision.')
    with connect() as conn, conn.cursor() as cur:
        job = _setting(cur, PREFIX + job_id)
        result = job.get('result')
        if not result or revision(result) != expected_revision:
            raise ValueError('Audit changed; reload before reviewing this proposal.')
        proposal = next((row for row in result['proposals'] if row['id'] == proposal_id), None)
        if not proposal:
            raise ValueError('Proposal not found.')
        _put(cur, REVIEW_PREFIX + job_id + ':' + proposal_id, {
            'job_id': job_id, 'proposal_id': proposal_id, 'revision': expected_revision,
            'decision': decision, 'reviewed_at': now(), 'reviewed_by': user['id']})


def revision(result):
    def stable(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value
    return hashlib.sha256(json.dumps(stable(result), sort_keys=True).encode()).hexdigest()


def run(stop):
    while not stop.is_set():
        try:
            process_one(stop)
        except Exception as error:
            LOG.warning('seo_companion_poll_unavailable error_type=%s', type(error).__name__)
        stop.wait(30)
