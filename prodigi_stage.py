"""Optimistic browser stages: short reads, external checks, atomic guarded commit.

No Save/Select/shipping permit is returned until every observed preparation is
rechecked under the existing browser lock. A concurrent Reset or sibling change
discards the entire result, including successful network readback.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from threading import BoundedSemaphore
import time

import prodigi_preparation as prep
from companion_poll_transaction import connection

_slots = BoundedSemaphore(2)
_current = ContextVar('prodigi_browser_stage', default=None)
_source_reads = ContextVar('prodigi_source_reads', default=None)


class Changed(ValueError):
    pass


class Stage:
    def __init__(self, lock):
        self.lock = lock
        self.observations = []
        self.pending = {}
        self.rows = []
        self.started = time.monotonic()

    def execute(self, sql, params=()):
        # Deliberately limited to the browser preparation store. Writes use save.
        if not sql.lstrip().upper().startswith('SELECT ') or 'FROM app_settings' not in sql:
            raise ValueError('Unsupported browser planning read.')
        with connection(prep.connect, slots=_slots) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        self.observations.append((sql, params, deepcopy(rows)))
        self.rows = deepcopy(rows)

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def save(self, key, value):
        if not any(any(row.get('key') == key for row in rows) for _, _, rows in self.observations):
            raise ValueError('An unread preparation cannot be changed by this stage.')
        self.pending[key] = deepcopy(value)

    def commit(self):
        if not self.pending:
            return
        import prodigi_browser as browser
        with connection(prep.connect, slots=_slots) as conn, conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(%s)', (self.lock,))
            # Lock the actual records as well: Reset and supplier reconciliation
            # use their own locks. NOWAIT avoids tying up the polling pool.
            keys = sorted({r['key'] for _, _, rows in self.observations for r in rows if 'key' in r})
            cur.execute('SELECT key FROM app_settings WHERE key=ANY(%s) ORDER BY key FOR UPDATE NOWAIT', (keys,))
            cur.fetchall()
            for sql, params, before in self.observations:
                cur.execute(sql, params)
                if cur.fetchall() != before:
                    raise Changed('Order changed while checking it; the old handoff was discarded. Retry the current order.')
            for key, value in self.pending.items():
                value['planning_ms'] = round((time.monotonic() - self.started) * 1000)
                browser.save(cur, key, value)


@contextmanager
def edit(lock):
    stage = Stage(lock)
    token = _current.set(stage)
    try:
        yield stage
        stage.commit()
    finally:
        _current.reset(token)


def group_rows(sql, params):
    """Enroll sibling membership in the same atomic verification boundary."""
    stage = _current.get()
    if stage is not None:
        stage.execute(sql, params)
        return stage.fetchall()
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def stale_result(result):
    def decorate(fn):
        @wraps(fn)
        def guarded(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Changed:
                return deepcopy(result)
        return guarded
    return decorate


def resolver_once(resolver):
    """One authoritative source read per allocation in one verification phase.

    Callers create a new wrapper for each independent supplier readback. Nothing
    survives a request or crosses the before/after artwork-download boundary.
    """
    cache, shared = {}, {}
    def resolve(aid):
        if aid not in cache:
            token = _source_reads.set(shared)
            try:
                cache[aid] = deepcopy(resolver(aid))
            finally:
                _source_reads.reset(token)
        return deepcopy(cache[aid])
    return resolve


def source_read(kind, key, load):
    """Share order/mapping reads across siblings, only in one resolver phase."""
    cache = _source_reads.get()
    if cache is None:
        return load()
    identity = (kind, str(key))
    if identity not in cache:
        cache[identity] = deepcopy(load())
    return deepcopy(cache[identity])
