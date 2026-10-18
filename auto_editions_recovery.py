"""Persistent failed-backlog recovery. Reads never enqueue; release gated worker only.

The journal lives in the existing durable queue audit. Admission and its journal
entry commit together under the same locks as manual Retry. No new artwork,
colour approval, source membership, allocation or completion receipt is invented.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from worker_diagnostics import explain

ACTOR = 'automatic:backlog-recovery-v1'
EVENT = 'backlog_recovery_attempt'
TRANSIENT = {'DOWNLOAD_INTERRUPTED', 'UPLOAD_INTERRUPTED', 'CONNECTION_INTERRUPTED'}
COLOUR = {'PROFILE_MISSING', 'COLOUR_POLICY_PENDING'}
STRUCTURAL = {'NUMBER_LAYER', 'PLAQUE_AMBIGUOUS', 'NUMBER_FORMAT', 'EDITION_GEOMETRY', 'FONT_MISSING'}


def enabled():
    return os.getenv('AUTO_EDITIONS_BACKLOG_RECOVERY_ENABLED', '').lower() == 'true'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def fix_revision(category):
    # Relevant implementation, not every deployment: unrelated releases must not
    # replenish deterministic retry budgets.
    files = ['auto_editions_recovery.py']
    if category == 'Colour/provenance':
        files += ['auto_editions_colour.py', 'auto_editions_colour_policy.py',
                  'scripts/prepare_auto_editions.py', 'scripts/photoshop/prepare_auto_editions.jsx']
    elif category == 'Plaque/layers':
        files += ['auto_editions_onboarding.py']
    elif category == 'Upload/receipts':
        files += ['auto_editions_technical.py', 'auto_editions_cloud.py']
    else:
        files += ['scripts/studio/auto_editions_local.py']
    root = Path(__file__).parent
    return digest({name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files})


def classify(row, config):
    """Conservative eligibility from authoritative current checkpoint evidence."""
    replacement = row.get('replacement') or {}
    # A failed replacement is the current native attempt. Its retained package's
    # older technical error must never hide a newer deterministic failure.
    reason = (replacement.get('reason') if replacement.get('stage')=='Failed' else None) or row.get('technical_reason') or row.get('reason') or ''
    code = explain(reason)['code']
    lower = reason.lower()
    transient=code in TRANSIENT or 'transfer failed: timeouterror' in lower
    category = ('Colour/provenance' if code in COLOUR or 'embedded icc profile required' in lower
                else 'Plaque/layers' if code in STRUCTURAL
                else 'Upload/receipts' if lower in ('invalid dropbox file id.', 'complete immutable upload receipts required.')
                else 'Transfer limits' if code=='TRANSFER_LIMIT'
                else 'Upload/network' if transient or 'transfer failed:' in lower or 'checkpoint needs reconnection' in lower
                else 'Stale/source' if code == 'SOURCE_CHANGED'
                else 'Photoshop' if 'photoshop' in lower or 'preparation failed' in lower
                else 'Other')
    result = dict(category=category, action=None, reason=reason, max_attempts=1)
    if row.get('status') not in ('Blocked', 'Needs PSD Repair'):
        return {**result, 'reason': 'Existing active, queued or verified checkpoint is protected.'}
    if row.get('priority', 0) <= 0:
        return {**result, 'reason': 'Excluded or deferred by the existing priority policy.'}
    pending = row.get('replacement') or {}
    if pending.get('manual_required') or (row.get('reset_cancellation') or {}).get('stage') in ('Cancelling', 'Confirmed'):
        return {**result, 'reason': 'Resolve the recorded mapping/reset cancellation first.'}
    if pending.get('stage') in ('Discovering', 'Queued', 'Preparing'):
        return {**result, 'reason': 'An owned replacement is already in progress.'}
    source = pending.get('source') if pending.get('stage') == 'Failed' else row.get('source')
    if not source or source.get('file_id') != row.get('dropbox_file_id'):
        return {**result, 'reason': 'Restore or explicitly resolve the current mapped source identity.'}
    if not row.get('preparation_hash') and pending.get('stage') not in ('Failed',):
        changed=current_source(row)
        if changed and changed.get('content_hash')!=source.get('content_hash'):
            return {**result,'category':'Stale/source','action':'retry',
                    'reason':'Mapped source has a new inventoried revision; inspect it under the current guarded pipeline.'}
    if category == 'Upload/network' and transient:
        return {**result, 'action': 'retry', 'max_attempts': 3}
    if category == 'Upload/receipts' and row.get('preparation_hash'):
        import auto_editions as ae
        manifest=row.get('manifest') or {}
        try:
            ae.validate_manifest(manifest)
            if ae.fingerprint(manifest)!=row['preparation_hash'] or manifest['source']!=source:
                raise ValueError('Retained package/source identity changed. Restore its evidence.')
            return {**result,'action':'retry'}
        except ValueError as error:
            return {**result,'reason':str(error)}
    if category == 'Colour/provenance':
        try:
            if row.get('preparation_hash'):
                # Reuse the exact certificate checks, including receipts, roles,
                # RGB8 evidence and existing colour policy. Tagged sources keep
                # their embedded ICC; never resolve a default for them.
                from auto_editions_technical import certificate, _colour_snapshot
                token = _colour_snapshot.set(config)
                try:
                    certificate(dict(hash=row['preparation_hash'], manifest=row['manifest'],
                                     proofs=row['proofs'], receipts=row['receipts']))
                finally:
                    _colour_snapshot.reset(token)
                return {**result, 'action': 'repair_exports'}
            from auto_editions_colour_policy import resolve
            resolve(source, **config)
            return {**result, 'action': 'retry'}
        except (ValueError, KeyError, TypeError) as error:
            return {**result, 'reason': str(error)+' Restore the embedded ICC or register independent, content-bound provenance within the existing approved workflow.'}
    # Historical generic errors can hide an already fixed colour failure. Only
    # pinned approved provenance permits one fresh inspection under current code;
    # it does not authorise assigning a profile to tagged/unknown source bytes.
    if reason == 'Preparation failed: RuntimeError. Existing PSD and mapping are preserved.':
        try:
            from auto_editions_colour_policy import resolve
            resolve(source, **config)
            return {**result, 'category': 'Colour/provenance', 'action': 'retry',
                    'reason': 'Historical preparation error; pinned colour provenance permits one current guarded attempt.'}
        except ValueError:
            pass
    if category == 'Plaque/layers':
        return {**result, 'reason': reason + ' Resolve the exact editable number and collector plaque in the source; no artwork target is inferred.'}
    return {**result, 'reason': reason + ' Retain diagnostics and establish a matching shared fix or source correction before retrying.'}


def current_source(row):
    source=(row.get('replacement') or {}).get('source') or row.get('source')
    meta=row.get('inventory_metadata')
    if meta and not row.get('preparation_hash') and not (row.get('replacement') or {}).get('stage')=='Failed':
        import psd_directory
        from auto_editions import source_identity
        if psd_directory.approved_file(meta) and meta.get('id')==row.get('dropbox_file_id'):
            return source_identity(row['product_gid'],meta)
    return source


SQL = """SELECT q.*,m.dropbox_file_id,p.manifest,p.proofs,p.receipts,i.metadata AS inventory_metadata,
 t.state AS technical_state,t.reason AS technical_reason
 FROM auto_edition_onboarding q
 LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
 LEFT JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
 LEFT JOIN auto_edition_source_inventory i ON i.file_id=m.dropbox_file_id
 LEFT JOIN auto_edition_technical_checks t ON t.product_gid=q.product_gid
  AND t.preparation_hash=q.preparation_hash AND t.checkpoint_at=q.updated_at"""


def key(row, decision, config):
    policy=None
    if decision['category']=='Colour/provenance':
        source=(row.get('replacement') or {}).get('source') or row.get('source') or {}
        from auto_editions_colour_policy import resolve
        try:policy=resolve(source,**config)[1]
        except (ValueError,KeyError):policy='unapproved'
    return digest(dict(source=row.get('source'), current_source=current_source(row),replacement_source=(row.get('replacement') or {}).get('source'),
                       preparation=row.get('preparation_hash'), category=decision['category'],
                       fix=fix_revision(decision['category']),
                       policy=policy))


def history(cur, pid, fingerprint):
    cur.execute("""SELECT created_at,detail FROM auto_edition_onboarding_audit
        WHERE product_gid=%s AND event=%s AND detail->>'fingerprint'=%s ORDER BY id""",
        (pid, EVENT, fingerprint))
    return cur.fetchall()


def budget(events, maximum, now=None):
    now = now or datetime.now(timezone.utc)
    if len(events) >= maximum:
        return 'Retry limit reached for unchanged source, policy and shared fix. Inspect retained failure evidence.'
    if events:
        from worker_health import stamp
        due = stamp(events[-1]['created_at']).timestamp() + min(60 * 2 ** (len(events)-1), 900)
        if now.timestamp() < due:
            return 'Waiting for capped retry backoff.'
    return ''


def plan(connect, config):
    """Full authoritative backlog; independent of the 50-row UI pagination."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SQL + " WHERE q.status IN ('Blocked','Needs PSD Repair') ORDER BY CASE WHEN q.priority=8 THEN 11 ELSE q.priority END DESC,q.created_at,q.product_gid")
        rows = cur.fetchall()
        result = []
        for row in rows:
            decision = classify(row, config)
            fingerprint = key(row, decision, config)
            waiting = budget(history(cur, row['product_gid'], fingerprint), decision['max_attempts']) if decision['action'] else ''
            from worker_health import stamp
            lease=stamp(row.get('lease_until'))
            if decision['action'] and lease and lease>datetime.now(timezone.utc):
                waiting='An active lease protects this checkpoint.'
            result.append(dict(row=row, decision=decision, fingerprint=fingerprint, waiting=waiting))
    return result


def scan(connect, read_metadata, *, limit=3):
    """Startup and periodic bounded admission; one blocked design cannot halt peers."""
    if not enabled():
        return []
    if not 1 <= limit <= 10:
        raise ValueError('Bounded recovery batch required.')
    from auto_editions_colour_store import configuration
    def read_config(connection):
        try:return configuration(connection)
        except (ValueError,OSError):
            # No colour authority is inferred when its registry is unavailable.
            # Network/checkpoint recovery can still progress independently.
            return dict(policies=[],memberships=[],default_group='')
    config = read_config(connect)
    from auto_editions import source_identity
    from auto_editions_onboarding_store import Queue
    from worker_health_queue import submit
    from worker_health import control, stamp
    accepted = []; attempted = 0
    items = plan(connect, config)
    for item in items:
        if attempted >= limit:
            break
        row = item['row']; decision = item['decision']; pid = row['product_gid']
        if not decision['action'] or item['waiting']:
            continue
        attempted += 1
        try:
            source = current_source(row)
            # Provider I/O stays outside the queue transaction. Claim/import repeat
            # current-source verification before touching or publishing any bytes.
            if source_identity(pid, read_metadata(source['file_id'])) != source:
                raise ValueError('Provider source changed. Resolve the exact mapping before retrying.')
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='800ms'; SET LOCAL statement_timeout='4000ms'")
                cur.execute('LOCK TABLE edition_products,product_psd_mappings,auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
                if control(cur)['paused']:
                    break
                cur.execute(SQL + ' WHERE q.product_gid=%s', (pid,))
                fresh = cur.fetchone()
                if not fresh or digest(fresh) != digest(row):
                    continue
                lease = stamp(fresh.get('lease_until'))
                if lease and lease > datetime.now(timezone.utc):
                    continue
                # Policy changes between planning and admission fail closed.
                @contextmanager
                def borrowed():
                    yield conn
                current_config = read_config(borrowed)
                current_decision = classify(fresh, current_config)
                fingerprint = key(fresh, current_decision, current_config)
                if fingerprint != item['fingerprint'] or current_decision['action'] != decision['action']:
                    continue
                events = history(cur, pid, fingerprint)
                if budget(events, decision['max_attempts']):
                    continue
                request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, pid + fingerprint + str(len(events))))
                submit(borrowed, pid, ACTOR, request_id, repair_confirmed=decision['action'] == 'repair_exports')
                Queue.audit(cur, pid, ACTOR, EVENT, dict(fingerprint=fingerprint, attempt=len(events)+1,
                    action=decision['action'], category=decision['category'], source=source,
                    previous_reason=decision['reason'], request_id=request_id))
                accepted.append(pid)
        except Exception as error:
            # Persist failed admission too: a bad source/guard must not monopolise
            # every periodic batch. The same key/backoff/ceiling applies.
            with connect() as conn, conn.cursor() as cur:
                cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
                events = history(cur, pid, item['fingerprint'])
                if not budget(events, decision['max_attempts']):
                    Queue.audit(cur,pid,ACTOR,EVENT,dict(fingerprint=item['fingerprint'],
                        attempt=len(events)+1,accepted=False,category=decision['category'],
                        reason=str(error)[:500]))
            import logging
            logging.getLogger(__name__).warning('backlog_recovery_admission_deferred product=%s error_type=%s', pid, type(error).__name__)
    # A compact durable heartbeat, explicitly discovery/admission, never success.
    # Health combines it with current queue states and verified upload evidence.
    from collections import Counter
    detail = dict(categories=dict(Counter(i['decision']['category'] for i in items)),
                  eligible=sum(bool(i['decision']['action']) and not i['waiting'] for i in items),
                  needs_review={i['row']['product_gid']: i['waiting'] or i['decision']['reason']
                                for i in items if not i['decision']['action'] or i['waiting'].startswith('Retry limit')},
                  backoff=sum(i['waiting']=='Waiting for capped retry backoff.' for i in items),
                  admitted=accepted)
    with connect() as conn, conn.cursor() as cur:
        Queue.audit(cur,'auto-editions-worker-control',ACTOR,'backlog_recovery_scan',detail)
    return accepted
