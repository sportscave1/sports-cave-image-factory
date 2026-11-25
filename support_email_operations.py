"""Bounded, content-free Email operational measurements and admin-only reports."""
from collections import Counter, deque
from datetime import datetime, timezone
import math
import logging
import threading
import time

SERIES = {'imap_read_ms', 'imap_write_ms', 'queue_wait_ms', 'certificate_poll_ms'}
NETWORK_CODES = {'connection', 'reset', 'network', 'timeout', 'bye', 'limit',
                 'authentication', 'configuration', 'tls', 'dns', 'tcp'}
THRESHOLDS = {'poll_stale_seconds': 120, 'backlog_warning_seconds': 120,
              'backlog_critical_seconds': 300, 'queue_warning_seconds': 120,
              'queue_critical_seconds': 600, 'sent_copy_warning_seconds': 300}


def age_seconds(value, now):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return None
        return round(max(0, now - stamp.timestamp()), 1)
    except (ValueError, TypeError, OverflowError):
        return None


def distribution(values):
    values = sorted(values)
    if not values:
        return {'count': 0, 'p50_ms': None, 'p95_ms': None}
    return {'count': len(values), 'p50_ms': round(values[math.ceil(len(values)*.5)-1], 2),
            'p95_ms': round(values[math.ceil(len(values)*.95)-1], 2)}


class OperationalMetrics:
    def __init__(self, clock=time.time):
        self.clock, self.lock = clock, threading.Lock()
        self.samples = {name: deque(maxlen=200) for name in SERIES}
        self.failures = deque(maxlen=200)
        self.polls = deque(maxlen=200)

    def observe(self, name, value):
        if name not in SERIES or isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        if not math.isfinite(value) or not 0 <= value <= 900000:
            return
        with self.lock:
            self.samples[name].append(float(value))

    def connection_failed(self, code):
        if code in NETWORK_CODES:
            with self.lock:
                self.failures.append((self.clock(), code))

    def poll(self, outcome, duration_ms, retry_seconds=0):
        if outcome not in {'success', 'idle', 'failed', 'waiting'}:
            return
        self.observe('certificate_poll_ms', duration_ms)
        with self.lock:
            self.polls.append((self.clock(), outcome, max(0, min(900, retry_seconds))))

    def snapshot(self):
        with self.lock:
            now = self.clock()
            failures = [code for stamp, code in self.failures if stamp >= now-300]
            polls = [outcome for stamp, outcome, _ in self.polls if stamp >= now-300]
            latest = self.polls[-1] if self.polls else None
            return {'scope': 'this process; last 200 samples per series; failures/polls in last 5 minutes',
                    'connection_failures_5m': len(failures), 'failure_codes_5m': dict(Counter(failures)),
                    'certificate_polls_5m': dict(Counter(polls)),
                    'last_poll_outcome': latest[1] if latest else 'not observed',
                    'last_poll_age_seconds': round(now-latest[0], 1) if latest else None,
                    'next_poll_delay_seconds': latest[2] if latest else None,
                    'latency': {name: distribution(values) for name, values in self.samples.items()}}


METRICS = OperationalMetrics()
LOG = logging.getLogger(__name__)


def backlog_progress(config, current, cursor, now):
    """Counts only the bounded header window; never store sender, subject or UID."""
    same = str(cursor['uidvalidity']) == str(current['uidvalidity'])
    pending = [h for h in current.get('messages', ()) if same and int(h['uid']) > int(cursor['last_uid'])]
    limited = same and int(current.get('last_uid', 0)) < int(current.get('uidnext', 1))-1
    dates = [h.get('received_at') for h in pending if isinstance(h.get('received_at'), datetime) and h['received_at'].tzinfo is not None]
    return {'pending_visible_count': len(pending), 'pending_window_limited': limited,
            'oldest_pending_received_at': min(dates).isoformat() if dates else None,
            'backlog_observed_at': (config.get('backlog_observed_at') or now) if pending or limited else None}


def poll_delay(progress):
    return 5 if progress.get('pending_visible_count') or progress.get('pending_window_limited') else 30


def report(config, outbound, process, browser=None, *, now=None):
    now = time.time() if now is None else now
    enabled = bool(config.get('enabled'))
    poll_age = age_seconds(config.get('checked_at'), now)
    started_age = age_seconds(config.get('changed_at'), now)
    backlog_age = age_seconds(config.get('oldest_pending_received_at') or config.get('backlog_observed_at'), now)
    queue_age = age_seconds(outbound.get('oldest_queued_at'), now)
    copy_age = age_seconds(outbound.get('oldest_copy_pending_at'), now)
    alerts = []
    def alert(code, severity, message):
        alerts.append({'code': code, 'severity': severity, 'message': message})
    if enabled and (poll_age is not None and poll_age > THRESHOLDS['poll_stale_seconds'] or
                    poll_age is None and (started_age is None or started_age > THRESHOLDS['poll_stale_seconds'])):
        alert('poll_stale', 'critical', 'The certificate worker has not completed a recent mailbox check. Check connection and worker logs; keep its cursor.')
    if enabled and backlog_age is not None and backlog_age > THRESHOLDS['backlog_warning_seconds']:
        alert('backlog', 'critical' if backlog_age > THRESHOLDS['backlog_critical_seconds'] else 'warning',
              'Certificate mail is waiting. Automatic catch-up continues when mailbox access is available.')
    if queue_age is not None and queue_age > THRESHOLDS['queue_warning_seconds']:
        alert('queue_age', 'critical' if queue_age > THRESHOLDS['queue_critical_seconds'] else 'warning',
              'Outgoing mail is waiting longer than expected. Inspect the outbox worker without creating another send.')
    if outbound.get('unknown_count', 0):
        alert('uncertain_delivery', 'warning', 'A delivery outcome is uncertain. Reconcile the original reply; do not resend.')
    if copy_age is not None and copy_age > THRESHOLDS['sent_copy_warning_seconds']:
        alert('sent_copy_lag', 'warning', 'Sent-folder copies are delayed. Accepted replies must not be sent again.')
    if process.get('connection_failures_5m', 0) >= 3:
        alert('repeated_connection_failures', 'warning', 'Repeated mailbox connection failures need provider or hosting investigation.')
    return {'observed_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
            'state': 'needs_attention' if alerts else 'off' if not enabled else 'warming_up' if poll_age is None else 'healthy',
            'certificate_enabled': enabled, 'last_successful_poll_at': config.get('checked_at'),
            'last_successful_poll_age_seconds': poll_age, 'oldest_pending_age_seconds': backlog_age,
            'pending_visible_count': config.get('pending_visible_count', 0),
            'pending_window_limited': bool(config.get('pending_window_limited')),
            'oldest_queued_age_seconds': queue_age, 'oldest_sent_copy_age_seconds': copy_age,
            'unknown_count': outbound.get('unknown_count', 0), 'copy_pending_count': outbound.get('copy_pending_count', 0),
            'alerts': alerts, 'thresholds': dict(THRESHOLDS), 'process': process,
            'browser_selection': browser_summary(browser)}


def browser_summary(value):
    """Whitelist untrusted aggregate browser timing; never echo arbitrary fields."""
    result = {}
    if not isinstance(value, dict):
        return result
    for name in ('cold_header', 'cold_body', 'cached_header', 'cached_body'):
        row = value.get(name)
        if not isinstance(row, dict):
            continue
        count = row.get('count')
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 200:
            continue
        clean = {'count': count}
        for key in ('p50_ms', 'p95_ms'):
            number = row.get(key)
            if number is None or (not isinstance(number, bool) and isinstance(number, (int, float))
                                  and math.isfinite(number) and 0 <= number <= 900000):
                clean[key] = number
        result[name] = clean
    return result


def diagnostics(mailbox, outbound, browser=None):
    import inbox_certificate_replies as replies
    import inbox_companion as state
    config = state.read(replies.SETTING)
    if str(config.get('mailbox', '')).casefold() != mailbox.casefold():
        config = {}
    return report(config, outbound, METRICS.snapshot(), browser)


class HealthMonitor:
    """One DB-only health check per minute; never controls mailbox work or sends."""
    def __init__(self, loader=None, clock=time.monotonic):
        self.loader, self.clock = loader, clock
        self.lock = threading.Lock()
        self.next_check = 0
        self.last_signature = None
        self.last_log = 0

    def check(self, mailbox):
        if not self.lock.acquire(blocking=False):
            return
        try:
            now = self.clock()
            if now < self.next_check:
                return
            self.next_check = now + 60
            if self.loader:
                value = self.loader(mailbox)
            else:
                from support_email_durable import REGISTRY
                value = diagnostics(mailbox, REGISTRY.store.diagnostics(mailbox))
            codes = tuple(sorted(a['code'] for a in value['alerts']))
            signature = value['state'], codes
            if signature != self.last_signature or now-self.last_log >= 300:
                log = LOG.warning if codes else LOG.info
                log('email_operations_health state=%s alert_codes=%s', value['state'], ','.join(codes) or 'none')
                self.last_signature, self.last_log = signature, now
            return value
        except Exception as error:
            # Diagnostics failure cannot stop mailbox recovery, advance a cursor
            # or cause a resend. Never log DB errors containing connection strings.
            LOG.warning('email_operations_check_unavailable category=%s', type(error).__name__)
        finally:
            self.lock.release()
