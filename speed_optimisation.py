"""Daily speed evidence, selection and durable reports. No app startup or deploys."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import uuid
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo('Australia/Sydney')
PREFIX = 'speed_report:v1:'
MAX_BYTES = 96_000
RETENTION_DAYS = 90
MAX_REPORTS_PER_DAY = 5  # Allows corrections without unlimited report growth.
STATUSES = {'reviewed', 'prepared', 'blocked', 'no_change', 'released', 'release_failed'}
SHA = re.compile(r'[0-9a-f]{40}')


def sydney_day(now=None):
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(TIMEZONE).date().isoformat()


def text(value, name, limit=3000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'Invalid {name}.')
    return value.strip()


def validate_report(value):
    if not isinstance(value, dict):
        raise ValueError('Expected a report object.')
    allowed = {'id', 'date', 'section', 'fingerprint', 'status', 'summary', 'base_sha',
               'candidate_sha', 'live_sha', 'measurements', 'tests', 'phases', 'blockers', 'files',
               'cleanup_checks', 'storage_checks'}
    if set(value) - allowed:
        raise ValueError('Unknown report fields.')
    result = dict(value)
    result['id'] = str(uuid.UUID(value['id']))
    result['date'] = dt.date.fromisoformat(value['date']).isoformat()
    if result['date'] > sydney_day():
        raise ValueError('Future report dates are not accepted.')
    for name in ('section', 'status', 'summary', 'fingerprint', 'base_sha'):
        result[name] = text(value.get(name), name, 3000 if name == 'summary' else 200)
    if result['status'] not in STATUSES or not re.fullmatch(r'[0-9a-f]{64}', result['fingerprint']):
        raise ValueError('Invalid status or source fingerprint.')
    for name in ('base_sha', 'candidate_sha', 'live_sha'):
        if value.get(name) and not SHA.fullmatch(value[name]):
            raise ValueError(f'Invalid {name}.')
    for name in ('tests', 'phases', 'blockers', 'files', 'cleanup_checks', 'storage_checks'):
        if name not in value and name in {'cleanup_checks', 'storage_checks'}:
            continue
        rows = value.get(name, [])
        if not isinstance(rows, list) or len(rows) > 40:
            raise ValueError(f'Invalid {name}.')
        result[name] = [text(row, name, 1000) for row in rows]
    measurements = value.get('measurements', [])
    if not isinstance(measurements, list) or len(measurements) > 30:
        raise ValueError('Invalid measurements.')
    for row in measurements:
        if not isinstance(row, dict) or set(row) != {'workflow', 'environment', 'revision', 'samples_ms'}:
            raise ValueError('A measurement needs workflow, environment, revision and samples_ms.')
        text(row['workflow'], 'workflow', 200)
        if row['environment'] not in {'live', 'baseline', 'candidate'} or not SHA.fullmatch(str(row['revision'])):
            raise ValueError('Invalid measurement environment or revision.')
        samples = row['samples_ms']
        if not isinstance(samples, list) or not 3 <= len(samples) <= 30:
            raise ValueError('Record 3 to 30 samples per workflow.')
        if any(type(n) not in (float, int) or not math.isfinite(n) or n <= 0 for n in samples):
            raise ValueError('Timing samples must be finite positive milliseconds.')
    result['measurements'] = measurements
    if result['status'] == 'released':
        if not value.get('candidate_sha') or value.get('candidate_sha') != value.get('live_sha'):
            raise ValueError('Released requires matching candidate and live revisions.')
        if not any(m['environment'] == 'live' and m['revision'] == value['live_sha'] for m in measurements):
            raise ValueError('Released requires repeat live timings at the released revision.')
    if len(json.dumps(result, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('Report too large.')
    return result


class Reports:
    """One immutable app_settings key per run; retries cannot overwrite evidence."""
    def __init__(self, connect):
        self.connect = connect

    def publish(self, value):
        report = validate_report(value)
        key = PREFIX + report['date'] + ':' + report['id']
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (PREFIX,))
                cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
                existing = cur.fetchone()
                if not existing:
                    cur.execute('SELECT count(*) AS reports FROM app_settings WHERE key LIKE %s',
                                (PREFIX + report['date'] + ':%',))
                    if cur.fetchone()['reports'] >= MAX_REPORTS_PER_DAY:
                        raise ValueError('Daily Speed report limit reached; retry the existing report ID.')
                cur.execute('''INSERT INTO app_settings(key, value, updated_at)
                    VALUES (%s, %s::jsonb, now()) ON CONFLICT (key) DO NOTHING''',
                            (key, json.dumps(report, allow_nan=False)))
                cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
                stored = cur.fetchone()['value']
                if stored != report:
                    raise ValueError('Report ID already exists with different evidence.')
                self._prune(cur)
            conn.commit()
        return report

    def _prune(self, cur):
        # Only compact Speed reports expire. No shared settings, orders, assets,
        # ledgers, provider history or customer data can match this namespace.
        cutoff = (dt.date.fromisoformat(sydney_day()) - dt.timedelta(days=RETENTION_DAYS - 1)).isoformat()
        pattern = PREFIX + '____-__-__:________-____-____-____-____________'
        cur.execute('''DELETE FROM app_settings WHERE key IN (
            SELECT key FROM app_settings WHERE key LIKE %s AND key < %s
            ORDER BY key LIMIT 500)''', (pattern, PREFIX + cutoff))

    def storage_review(self):
        """Aggregate-only read: never reads customer rows or deletes application data."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '3s'")
                cur.execute('''SELECT count(*) AS reports,
                    COALESCE(sum(octet_length(value::text)),0) AS bytes
                    FROM app_settings WHERE key LIKE %s''', (PREFIX + '%',))
                speed = {key: int(value) for key, value in cur.fetchone().items()}
                cur.execute('''SELECT schemaname, relname AS table_name,
                    n_live_tup AS estimated_rows, n_dead_tup AS estimated_dead_rows,
                    pg_total_relation_size(relid) AS bytes
                    FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15''')
                tables = [dict(row) for row in cur.fetchall()]
        return {'speed_reports': speed, 'largest_tables': tables,
                'retention_days': RETENTION_DAYS, 'automatic_deletion_scope': PREFIX,
                'application_data_deleted': False}

    def recent(self, limit=60):
        limit = max(1, min(100, int(limit)))
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute('''SELECT value FROM app_settings WHERE key LIKE %s
                    ORDER BY key DESC LIMIT %s''', (PREFIX + '%', limit))
                return [row['value'] for row in cur.fetchall()]


def fingerprint(root, files):
    root = Path(root).resolve()
    hasher = hashlib.sha256()
    for name in sorted(set(files)):
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Source file missing or outside workspace: ' + name)
        hasher.update(name.encode() + b'\0' + path.read_bytes() + b'\0')
    return hasher.hexdigest()


def prioritise(sections, reports):
    """New/changed sections first; then regressions, then oldest reviewed section."""
    latest = {}
    for row in reports:
        key = row['section']
        if key not in latest or row['date'] > latest[key]['date']:
            latest[key] = row
    def rank(section):
        previous = latest.get(section['name'])
        untouched = not previous or previous['fingerprint'] != section['fingerprint']
        return (not untouched, -float(section.get('regression_ms', 0)),
                previous['date'] if previous else '', section['name'])
    return sorted(sections, key=rank)
