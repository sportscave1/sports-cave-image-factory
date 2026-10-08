"""Lightweight shared mailbox status and durable events in the existing OS stores.

No connection at import. No message-body, attachment, order or workspace dependency.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from support_email_provider import ImapProvider, MailboxError, load_configuration
from support_email_runtime import POLL_SECONDS

LOGGER = logging.getLogger(__name__)
EVENT = "new_email_received"
TTL = POLL_SECONDS
STALE_TTL = 120
_LOCK = threading.Lock()
_CACHE = {"scope": None, "expires": 0, "success": 0, "value": {}, "dirty": False}
_INVALIDATION = 0
_REFRESH_LOCK = threading.Lock()
_REFRESH_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='email-count')
_REFRESH = None


def cached_status(scope):
    # Credential-scoped, counts only. Never share another account's snapshot.
    if _CACHE['scope'] != scope or not _CACHE['value']:
        return {'available': False, 'unread_count': None}
    return dict(_CACHE['value'])


def fast_status():
    """Return immediately; one coalesced provider refresh serves all browser tabs."""
    global _REFRESH
    cfg = load_configuration()
    if not cfg.configured:return {'available': False, 'unread_count': None}
    with _REFRESH_LOCK:
        if (_REFRESH is None or _REFRESH.done()) and (
                _CACHE['scope'] != cfg.scope or time.time() >= _CACHE['expires']):
            _REFRESH = _REFRESH_POOL.submit(status, configuration=cfg)
        pending = bool(_REFRESH and not _REFRESH.done())
    result = cached_status(cfg.scope)
    return {**result, 'refreshing': pending,
            'stale': not result.get('available') or time.time()-result.get('checked_at',0)>TTL}


def state_key(mailbox):
    return "email_notification_cursor_v1:" + hashlib.sha256(mailbox.casefold().encode()).hexdigest()


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def event_metadata(mailbox, message):
    """Explicit allowlist: never accept arbitrary provider dictionaries for storage."""
    sender = message.get("sender") or {}
    date = message.get("date") or message.get("received_at")
    return {"mailbox": mailbox.casefold(), "folder": "INBOX",
            "uidvalidity": str(message["uidvalidity"]), "uid": str(message["uid"]),
            "message_id": _text(message.get("message_id"), 998),
            "sender_name": _text(sender.get("name"), 160),
            "sender_email": _text(sender.get("email"), 254),
            "subject": _text(message.get("subject"), 240),
            "received_at": date.isoformat() if isinstance(date, datetime) else _text(date, 80)}


class NotificationStore:
    """Reuse app_sync_state cursors and audit_logs events; no new table or schema."""
    def poll(self, provider, *, now, force=False):
        import supabase_backend
        mailbox = provider.configuration.address
        key = state_key(mailbox)
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='1500ms'")
                cur.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS acquired", (key,))
                if not (cur.fetchone() or {}).get("acquired"):
                    return None
                cur.execute("SELECT value FROM app_sync_state WHERE key=%s FOR UPDATE", (key,))
                previous = (cur.fetchone() or {}).get("value") or {}
                if isinstance(previous, str):
                    previous = json.loads(previous)
                if not force and now - float(previous.get("checked_at", 0)) < TTL:
                    return previous
                snapshot = provider.notification_snapshot(previous)
                for message in snapshot["messages"]:
                    metadata = event_metadata(mailbox, message)
                    identity = hashlib.sha256(json.dumps([mailbox.casefold(), "INBOX",
                        metadata["uidvalidity"], metadata["uid"]]).encode()).hexdigest()
                    metadata["event_key"] = identity
                    payload = {"action_type": EVENT, "page": "Email", "message": "New email", "metadata": metadata}
                    # Cursor and events commit together under the mailbox lock. The identity
                    # check also tolerates a cursor restored from an older database backup.
                    cur.execute("""INSERT INTO audit_logs(event_type,entity_type,entity_id,new_value,reason,actor,source)
                        SELECT %s,'email_notification',%s,%s::jsonb,'New email','sports_cave_os','Email'
                        WHERE NOT EXISTS (SELECT 1 FROM audit_logs WHERE event_type=%s
                            AND entity_type='email_notification' AND entity_id=%s)""",
                        (EVENT, identity, json.dumps(payload), EVENT, identity))
                state = {"uidvalidity": snapshot["uidvalidity"], "last_uid": snapshot["last_uid"],
                         "unread_count": snapshot["unseen"], "checked_at": now}
                cur.execute("""INSERT INTO app_sync_state(key,value,cursor_value,status,updated_at)
                    VALUES (%s,%s::jsonb,%s,'ready',now()) ON CONFLICT(key) DO UPDATE SET
                    value=EXCLUDED.value,cursor_value=EXCLUDED.cursor_value,status='ready',updated_at=now()""",
                    (key, json.dumps(state), str(state["last_uid"])))
            conn.commit()
        return state


def invalidate():
    """Called only after an explicit Email refresh or confirmed mailbox action."""
    global _INVALIDATION
    # Never wait behind an in-flight network poll on the interactive Email thread.
    _INVALIDATION += 1
    _CACHE["expires"] = 0
    _CACHE["dirty"] = True


def status(*, configuration=None, provider=None, store=None, now=None):
    cfg = configuration or load_configuration()
    if not cfg.configured:
        return {"available": False, "unread_count": None}
    clock = time.time() if now is None else now
    if not _LOCK.acquire(blocking=False):
        return {**cached_status(cfg.scope), 'stale': True}
    try:
        generation = _INVALIDATION
        if _CACHE["scope"] != cfg.scope:
            _CACHE.update(scope=cfg.scope, expires=0, success=0, value={}, dirty=False, failures=0)
        cached = dict(_CACHE["value"])
        if clock < _CACHE["expires"]:
            return {**cached, 'stale': clock - _CACHE['success'] > TTL}
        _CACHE["expires"] = clock + TTL  # Failures are throttled too.
        adapter = provider or ImapProvider(cfg, background=True)
        try:
            value = (store or NotificationStore()).poll(adapter, now=clock, force=_CACHE["dirty"])
            if value is None:
                return {**cached_status(cfg.scope), 'stale': True}
            result = {"available": True, "unread_count": int(value["unread_count"]),
                      "checked_at": float(value["checked_at"]),
                      "arrival_version": f'{value["uidvalidity"]}:{value["last_uid"]}'}
            _CACHE.update(value=result, success=clock, dirty=False, failures=0)
            return dict(result)
        except Exception as error:
            if getattr(error, "code", "") == "busy":
                _CACHE["expires"] = clock + 15
                return {**cached, 'stale': True} if cached else {
                    "available": False, "unread_count": None}
            if getattr(error, "code", "") != "deferred":
                LOGGER.warning("Email notification check unavailable (%s)", type(error).__name__)
            failures = min(4, _CACHE.get("failures", 0) + 1)
            _CACHE.update(failures=failures, expires=clock + min(120, 15 * 2 ** (failures - 1)))
            # No cursor means no arrival notifications. A count remains possible without
            # persistence, and is never fabricated as zero when either dependency fails.
            try:
                if isinstance(error, MailboxError):
                    raise error  # A failed IMAP operation must not immediately reconnect.
                count = adapter.get_unread_count()
                result = {"available": True, "unread_count": count, "checked_at": clock}
                _CACHE.update(value=result, success=clock, failures=0, expires=clock + TTL)
                return dict(result)
            except Exception:
                result = {**cached, "available": False, 'stale': True} if cached else {
                    "available": False, "unread_count": None}
                _CACHE["value"] = result
                return dict(result)
    finally:
        if generation != _INVALIDATION:
            _CACHE.update(expires=0, dirty=True)
        _LOCK.release()
