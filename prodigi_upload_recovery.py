"""Recover known pre-Save upload waits on the same independently checked draft.

Never recovers a consumed Save, a changed supplier item or a submitted order.
Transient UI waits back off without holding the Orders queue or discarding JPGs.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import logging
import re

import prodigi_browser as browser
import prodigi_preparation as prep
import prodigi_stage as stages

ERRORS = {
    'The expected Prodigi control did not finish loading.',
    'Prodigi did not reach the expected upload state.',
    'Prodigi image library authentication expired before image selection.',
    'The uploaded image did not become available in the Prodigi picker.',
    'The pinned JPG is unavailable.',
    'Pinned artwork transfer interrupted.',
    'Failed to fetch',
    'The exact Prodigi order page did not become ready; check its loading or sign-in state.',
    'Prodigi sign-in expired. Sign into Prodigi in Edge, then recheck this same order to resume. No supplier action was repeated.',
    'The draft changed before Save.',
}
STAGES = {'download','open','signin','readiness','row','editor','picker','transfer','uploaded','orientation','permit'}


def reusable_asset(provider, filename, snap):
    """A name alone is insufficient: verify metadata and the original JPG bytes."""
    matches = [a for a in provider.assets()
               if a.get('name') in (filename, filename.removesuffix('.jpg'))]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError('The previous uploaded JPG is ambiguous; review its library entry.')
    asset = matches[0]
    dims = asset.get('dimensions') or {}
    if (asset.get('sizeBytes') != snap['output']['bytes'] or asset.get('mimeType') != 'image/jpeg'
            or [dims.get('widthPx'), dims.get('heightPx')] != snap['dimensions']):
        raise ValueError('The previous uploaded JPG metadata changed.')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', str(asset.get('id', ''))):
        raise ValueError('The previous uploaded JPG identity is invalid.')
    return str(asset['id']) if browser.verify_file(asset['url'], snap['output']) else None


def recover(user):
    prep.require_user(user)
    from companion_poll_transaction import connection
    with connection(prep.connect) as conn, conn.cursor() as cur:
        cur.execute("""SELECT key FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
            AND value->>'status'='Needs review'
            AND value->'browser'->>'started'='false'
            AND value->'browser'->>'last_stage'=ANY(%s)
            AND value->'browser'->>'client_error'=ANY(%s)
            AND NOT value ? 'submission' AND NOT COALESCE((value->>'hidden')::boolean,false)
            AND COALESCE((value->'upload_recovery'->>'retry_at')::timestamptz,'epoch')<now()
            ORDER BY updated_at LIMIT 2""", (list(STAGES), list(ERRORS)))
        keys = [row['key'] for row in cur.fetchall()]
    recovered = 0
    for key in keys:
        try:
            result = recover_one(key)
            recovered += bool(result)
            if not result:defer(key)
        except Exception as error:
            # One unavailable draft must not cancel other ready orders' poll.
            logging.getLogger(__name__).warning('Orders upload recovery deferred kind=%s', type(error).__name__)
            try:defer(key)
            except Exception:pass # Database outage is retried by the next poll.
    return recovered


@stages.stale_result(None)
def defer(key):
    """Rotate an unavailable/changed candidate so it cannot starve later orders."""
    with stages.edit(browser.LOCK) as cur:
        value=browser.read(cur,key)
        if value.get('status')!='Needs review' or (value.get('browser') or {}).get('started') is not False:return
        value.setdefault('upload_recovery',{})['retry_at']=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
        browser.save(cur,key,value)


@stages.stale_result(False)
def recover_one(key):
    provider, resolver, _, sandbox = browser.context(key)
    if sandbox:
        return False
    with stages.edit(browser.LOCK) as cur:
        value = browser.read(cur, key)
        receipt = value.get('browser') or {}
        previous = value.get('upload_recovery') or {}
        if (value.get('status') != 'Needs review' or receipt.get('started') is not False
                or receipt.get('verified') or receipt.get('last_stage') not in STAGES
                or receipt.get('client_error') not in ERRORS or value.get('submission') or value.get('write_intent')):
            return False
        if previous.get('retry_at') and datetime.fromisoformat(previous['retry_at']) > datetime.now(timezone.utc):
            return False
        snap, order, item = browser.checked(value, provider, resolver, False)
        if (browser.has_existing_artwork(item) or (item.get('assets') or []) != receipt.get('empty_slots', [])
                or browser.business(order, item['id']) != receipt.get('before')):
            return False
        asset_id = reusable_asset(provider, receipt['filename'], snap)
        attempts = previous.get('attempts', 0) + 1
        recovery = dict(attempts=attempts, retry_at=(datetime.now(timezone.utc) +
            timedelta(seconds=min(900, 60 * 2 ** min(attempts - 1, 4)))).isoformat(),
            source_sha256=snap['output']['sha256'], filename=receipt['filename'],
            asset_id=asset_id, before=deepcopy(receipt['before']),
            empty_slots=deepcopy(receipt.get('empty_slots', [])))
        value['browser_history'] = (value.get('browser_history', []) + [
            {k:receipt.get(k) for k in ('claimed_at','filename','started','last_stage','client_error')}])[-8:]
        # Removing the old token and recording the replacement proof commit together.
        value.pop('browser'); value.pop('last_failure', None)
        value.update(upload_recovery=recovery, status=browser.WAITING,
            message='Recovering this unchanged empty item; reusing the verified uploaded JPG when available. No Save was repeated.')
        browser.save(cur, key, value)
        return True
