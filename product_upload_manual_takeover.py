"""Explicit manual recovery of one inactive upload hold; no provider mutations."""
from datetime import datetime, timezone
import json

from psd_mapping_store import MappingConflict


def prepare(cur, pid, metadata, actor, operation_id=None):
    """Called inside attach's transaction, BEFORE its mapping-table lock.

    Lock intake rows first, as Map does. NOWAIT refuses a worker currently inside
    a guarded provider mutation even if its recorded lease has already expired.
    All changes roll back if attachment or its ordinary validations fail.
    """
    from product_upload_mapping_hold import held
    if not held(cur, pid, metadata['id']):
        return False
    import os_accounts
    if not os_accounts.is_admin(actor):
        raise MappingConflict('An administrator must explicitly take over this retained Product Uploads mapping.')
    cur.execute("SELECT to_regprocedure('public.guard_upload_manual_takeover()') AS name")
    if not cur.fetchone()['name']:
        raise MappingConflict('Manual takeover migration is required; the retained mapping hold was not changed.')
    cur.execute("SELECT 1 FROM pg_trigger WHERE tgname='upload_manual_takeover_terminal' AND tgrelid='public.product_upload_intakes'::regclass AND tgenabled='O' AND NOT tgisinternal")
    if not cur.fetchone():
        raise MappingConflict('The manual takeover retry guard is unavailable. Nothing was changed.')
    cur.execute('SELECT * FROM product_upload_mapping_holds WHERE product_gid=%s OR file_id=%s', (pid,metadata['id']))
    holds = cur.fetchall()
    if len(holds) != 1 or holds[0]['product_gid'] != pid or holds[0]['file_id'] != metadata['id']:
        raise MappingConflict('The retained hold belongs to a different product or PSD. Nothing was changed.')
    hold = holds[0]
    try:
        cur.execute("""SELECT id,data FROM product_upload_intakes WHERE id=%s
            OR data->'upload_operation'->'source'->>'id'=%s
            OR data->'upload_operation'->>'product_id'=%s
            ORDER BY id FOR UPDATE NOWAIT""", (str(hold['operation_id']),metadata['id'],pid))
        rows = cur.fetchall()
    except Exception as error:
        if getattr(error, 'sqlstate', None) == '55P03':
            raise MappingConflict('A mapping worker is active. Wait for it to finish before manual takeover.') from error
        raise
    if not any(str(row['id']) == str(hold['operation_id']) for row in rows):
        raise MappingConflict('The hold-owning operation is unavailable. Nothing was changed.')
    now = datetime.now(timezone.utc)
    for row in rows:
        op = row['data'].get('upload_operation') or {}
        task = op.get('sync_map') or {}
        source = op.get('source') or {}
        if (source.get('id') != metadata['id'] or op.get('product_id') not in (None,pid)
                or row['data'].get('lifecycle')):
            raise MappingConflict('Conflicting retained PSD work needs review before manual takeover.')
        if task.get('lease_until') and datetime.fromisoformat(task['lease_until']) > now:
            raise MappingConflict('A mapping worker is active. Wait for it to finish before manual takeover.')
        if (not source.get('content_hash') or not metadata.get('rev') or
                any(source.get(k) != metadata.get(k) for k in ('id','content_hash','size'))):
            raise MappingConflict('The PSD content changed from the retained operation. Review that revision before takeover.')
    # Same admission-lock order as hold acquisition. A new preparation or Map
    # cannot slip between the inactivity check and the manual link commit.
    cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
    cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
    cur.execute('LOCK TABLE auto_edition_onboarding,auto_edition_jobs IN SHARE ROW EXCLUSIVE MODE')
    cur.execute('SELECT 1 FROM auto_edition_onboarding WHERE product_gid=%s OR file_id=%s', (pid,metadata['id']))
    if cur.fetchone():
        raise MappingConflict('Existing preparation work must be resolved before manual takeover.')
    cur.execute("""SELECT 1 FROM auto_edition_jobs WHERE
        (payload->'identity'->'source'->>'product_gid'=%s OR payload->'identity'->'source'->>'file_id'=%s)
        AND status IN ('Queued','Generating')""", (pid,metadata['id']))
    if cur.fetchone():
        raise MappingConflict('Rendering work is active. Manual takeover was not applied.')
    cur.execute("SELECT 1 FROM auto_edition_preparations WHERE manifest->'source'->>'product_gid'=%s OR manifest->'source'->>'file_id'=%s", (pid,metadata['id']))
    if cur.fetchone():
        raise MappingConflict('Retained preparation assets need review before manual takeover.')
    if str(operation_id or '') != str(hold['operation_id']):
        error = MappingConflict('This inactive Product Uploads attempt retains the PSD hold. Confirm manual takeover, then Save PSD again. Its progress will be preserved and its retries permanently stopped.')
        error.manual_takeover_operation = str(hold['operation_id'])
        raise error
    cur.execute("SELECT id FROM edition_products WHERE COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id)=%s", (pid,))
    editions = cur.fetchall()
    if len(editions) != 1:
        raise MappingConflict('The selected Edition Ops identity is missing or ambiguous.')
    receipt = dict(hold_operation_id=str(hold['operation_id']), product_gid=pid,
                   edition_id=editions[0]['id'], file_id=metadata['id'], actor_id=str(actor['id']),
                   verified_at=now.isoformat(), source=metadata)
    for row in rows:
        # Keep every move intent, moved receipt, completed step and error. The
        # separate terminal receipt fences both this attempt and sibling retries.
        op = row['data']['upload_operation']
        task = op.setdefault('sync_map', {})
        task.update(manual_takeover=receipt, state='Manually mapped', lease=None, lease_until=None, preparation_held=False)
        cur.execute('UPDATE product_upload_intakes SET data=%s::jsonb,updated_at=now() WHERE id=%s',
                    (json.dumps(row['data']),str(row['id'])))
    return True
