"""Durable file handoff. Companion polling retries file work, never Shopify writes."""
from datetime import datetime, timezone
from pathlib import PurePosixPath
import unicodedata
from product_upload_intake import Intakes
from product_upload_dropbox import REVIEW, verify_roots, within
import psd_directory


def now(): return datetime.now(timezone.utc).isoformat()


def filename(title):
    value = ''.join('_' if ord(c) < 32 or c in '<>:"/\\|?*' else c for c in unicodedata.normalize('NFC', title))
    value = value.strip(' .')
    if value.lower().endswith('.psd'): value = value[:-4].strip(' .')
    if not value: raise ValueError('The Shopify title has no usable filename characters.')
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}: value = '_' + value
    while len(value.encode('utf-8')) > 240: value = value[:-1]
    return value + '.psd'


def media_complete(product, data):
    required = len((data.get('mockups_context') or {}).get('images') or [])
    images = product.get('images') or []
    return bool(data.get('mockups_exported') and required >= 8 and len({x.get('id') or x.get('url') for x in images if x.get('url')}) >= required)


def confirm(service, key, actor, pid, shopify):
    import auto_editions as ae
    from product_upload_services import normal_title
    with service.store.locked(key, actor['id']) as (row, cur):
        d = row['data']
        if d.get('product_gid'):
            if d['product_gid'] != pid: raise ValueError('This PSD is already linked to another Shopify product.')
        else:
            previous = next((p for p in d.get('choices', []) if p['id'] == pid), None)
            if not previous or not d.get('copied') or not d.get('mockups_exported'):
                raise ValueError('Complete the current mockups and exact Shopify lookup first.')
            meta = service.provider.metadata_if_present(d['source']['id'])
            if not meta or any(meta.get(k) != d['source'].get(k) for k in ('id','rev','content_hash')):
                raise ValueError('The selected source changed; review it before linking.')
            product = shopify.fetch_product_by_shopify_id(pid)
            if product.get('shopify_product_id') != pid: raise ValueError('Shopify returned a different product identity.')
            if normal_title(product['title']) != normal_title(previous['title']): raise ValueError('Shopify title changed. Repeat the lookup.')
            state = product.get('status','').upper()
            if row['mode'] == 'DRAFT' and state != 'DRAFT': raise ValueError('The requested Shopify draft is not confirmed.')
            if row['mode'] == 'LIVE' and (state != 'ACTIVE' or not product.get('online_store_url')):
                raise ValueError('The requested Shopify publication is not confirmed.')
            existing = service.mappings.read()
            if any(p != pid and m['dropbox_file_id'] == meta['id'] for p,m in existing.items()) or pid in existing and existing[pid]['dropbox_file_id'] != meta['id']:
                raise ValueError('A different product/PSD mapping already exists. Use the established replacement workflow.')
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('product-file-link:'+meta['id'],))
            cur.execute("SELECT id FROM product_upload_intakes WHERE data->'source'->>'id'=%s AND data->>'product_gid' IS NOT NULL AND data->>'product_gid'<>%s LIMIT 1", (meta['id'],pid))
            if cur.fetchone(): raise ValueError('This exact PSD is already linked to another confirmed Shopify product.')
            # Persist confirmed product identity BEFORE any file work. This is
            # the durable link even if registration or path reconciliation fails.
            d.update(product_gid=pid, product_title=product['title'], product_url=product.get('admin_url',''),
                     bound_source=ae.source_identity(pid,meta), choices=[], state='Shopify confirmed',
                     shopify_completion='Draft confirmed' if state == 'DRAFT' else 'Published live',
                     lifecycle=dict(state='Queued', original_source=meta, expected_source=meta,
                                    actor={k:actor[k] for k in ('id','username','role','is_active','account_status','page_permissions') if k in actor},
                                    product_id=pid, queued_at=now(), history=[]))
    # Registration and mapping can fail independently; Companion resumes them
    # from the persisted confirmed ID, never creates or republishes a product.
    return service.store.read(key, actor['id'])


def handoff(row, provider, product):
    """Retry-safe provider boundary, also used by isolated fixture tests."""
    d = row['data']; task = d['lifecycle']; source = task['expected_source']
    if product.get('status','').upper() not in ('DRAFT','ACTIVE'): raise ValueError('The confirmed product is archived or unavailable. Review Shopify before retrying.')
    current = provider.metadata_if_present(source['id'])
    if not current or current.get('id') != source['id']:
        raise ValueError('Selected Dropbox source is unavailable. Restore access and retry.')
    roots = verify_roots(provider)
    live = product.get('status','').upper() == 'ACTIVE' and bool(product.get('online_store_url'))
    already_live = within(current['path_display'], roots['live']['path']) and not within(current['path_display'], roots['review']['path'])
    parent = roots['live']['path'] if already_live or live and media_complete(product,d) else roots['review']['path']
    destination = parent + '/' + filename(product['title'])
    intent = task.get('intent')
    # Recover a provider success whose DB acknowledgement was lost, using the
    # exact persisted intent, stable ID, and unchanged bytes. No filename match.
    recovered = bool(intent and current.get('path_display') == intent['to'] and current.get('content_hash') == source.get('content_hash'))
    if any(current.get(k) != source.get(k) for k in ('id','rev','content_hash','path_display')) and not recovered:
        raise ValueError('Source revision changed. Review the current PSD before retrying; previous results are retained.')
    if not (within(current['path_display'], REVIEW) or already_live): raise ValueError('Source moved outside the verified workflow folders.')
    target = provider.metadata_if_present(destination)
    if target and target['id'] != source['id']: raise ValueError('Destination conflict. Rename the other file or change the Shopify title, then retry. Nothing was overwritten.')
    if current['path_display'] != destination:
        if not intent or intent['to'] != destination:
            raise ValueError('Persist a current move intent before contacting Dropbox.')
        moved = provider.api.move_path(provider.token, source['id'], destination, root_path=provider.context['root_path'])
        if moved.get('id') != source['id'] or moved.get('content_hash') != source['content_hash']:
            raise ValueError('Source changed during handoff. Retain both receipts for review.')
        current = moved
    if source['path_display'] != current['path_display'] or not task['history']:
        task['history'].append(dict(old_path=source['path_display'], new_path=current['path_display'], completed_at=now(), revision=current['rev']))
    task.update(expected_source=current, state='Complete' if already_live or live and media_complete(product,d) else 'Waiting for publication/media', reason='', checked_at=now())
    d['source'] = current
    return current


def run_one(connect, provider, actor):
    """Called only by authenticated Companion claim, under existing claim fences.

    Poll waiting drafts once per minute so later publication completes the same
    checkpoint without a page visit. Errors remain visible and retryable.
    """
    store = Intakes(connect)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id FROM product_upload_intakes WHERE actor_id=%s
            AND data->>'workflow_version'='3' AND data->'lifecycle' IS NOT NULL
            AND (data->'lifecycle'->>'checked_at' IS NULL OR (data->'lifecycle'->>'checked_at')::timestamptz<now()-interval '60 seconds')
            AND data->'lifecycle'->>'state'<>'Complete' ORDER BY updated_at LIMIT 1""", (str(actor),))
        pending = cur.fetchone()
    if not pending: return False
    key = str(pending['id'])
    import shopify_sync
    # Read Shopify outside the locked native section; never a mutation API.
    row = store.read(key, actor)
    try:
        product = shopify_sync.fetch_product_by_shopify_id(row['data']['product_gid'])
        if product.get('shopify_product_id') != row['data']['product_gid']: raise ValueError('Shopify product identity changed.')
    except Exception:
        with store.locked(key, actor) as (current, cur):
            current['data']['lifecycle'].update(state='Error',reason='Shopify confirmation unavailable. The confirmed product link is retained; retry file handoff.',checked_at=now())
        return True
    with store.locked(key, actor) as (row, cur):
        task = row['data']['lifecycle']; current = task['expected_source']
        live = product.get('status','').upper() == 'ACTIVE' and bool(product.get('online_store_url')) and media_complete(product,row['data'])
        parent = psd_directory.ROOT if within(current['path_display'],psd_directory.ROOT) and not within(current['path_display'],REVIEW) or live else REVIEW
        # Intent commits before Dropbox I/O, including the original path.
        destination = parent+'/'+filename(product['title'])
        old_intent = task.get('intent')
        if old_intent and old_intent['to'] != destination:
            fresh = provider.metadata_if_present(current['id'])
            if fresh and all(fresh.get(k) == current.get(k) for k in ('id','rev','content_hash','path_display')):
                task.pop('intent')  # Old operation has not happened; update the reviewed title target.
            elif fresh and fresh.get('path_display') == old_intent['to'] and fresh.get('content_hash') == current['content_hash']:
                task['history'].append(dict(old_path=current['path_display'],new_path=fresh['path_display'],completed_at=now(),revision=fresh['rev'],recovered=True))
                task['expected_source']=fresh;task.pop('intent');current=fresh
        task.setdefault('intent', dict(source=current, to=destination, created_at=now()))
    with store.locked(key, actor, provider_io=True) as (row, cur):
        cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
        from worker_health import control
        if control(cur)['paused']:
            row['data']['lifecycle'].update(state='Waiting for processing',reason='Worker claims are paused; file handoff is retained.',checked_at=now())
            return False
        cur.execute("""SELECT 1 FROM auto_edition_onboarding WHERE
            status='Preparing' OR to_jsonb(auto_edition_onboarding)->'replacement'->>'stage'='Preparing' LIMIT 1""")
        if cur.fetchone():
            row['data']['lifecycle'].update(state='Waiting for processing',reason='Active or retained native preparation must be resolved before file handoff.',checked_at=now())
            return False
        cur.execute("SELECT 1 FROM product_upload_intakes WHERE data->'mockup_render'->>'state'='Rendering' LIMIT 1")
        if cur.fetchone():
            row['data']['lifecycle'].update(state='Waiting for processing',reason='A native PSD render still owns processing. File handoff will wait.',checked_at=now())
            return False
        cur.execute("SELECT 1 FROM product_upload_intakes WHERE data->'server_artwork'->>'state'='Preparing' LIMIT 1")
        if cur.fetchone():
            row['data']['lifecycle'].update(state='Waiting for processing',reason='Server artwork preparation is active. File handoff will wait.',checked_at=now())
            return False
        try:
            meta = handoff(row, provider, product)
            row['data']['bound_source'] = __import__('auto_editions').source_identity(row['data']['product_gid'],meta)
            row['data']['product_title'] = product['title']
            row['data']['shopify_completion'] = 'Published live' if product.get('status','').upper() == 'ACTIVE' and product.get('online_store_url') else 'Draft confirmed'
            if psd_directory.approved_file(meta): row['data']['lifecycle']['state']='Registering master'
            row['data']['lifecycle'].pop('intent',None)
        except Exception as error:
            row['data']['lifecycle'].update(state='Error', reason=str(error) if isinstance(error,ValueError) else 'File handoff unavailable; retry is queued. The confirmed Shopify product is retained.', checked_at=now())
    # Canonical registration/mapping opens its own transactions. Run only after
    # the native claim fence commits, never while holding its table lock.
    row = store.read(key,actor)
    if row['data']['lifecycle']['state'] == 'Registering master':
        try:
            from product_upload_services import Handoff
            service = Handoff(connect,provider); meta = row['data']['source']; pid = row['data']['product_gid']
            fresh = provider.metadata_if_present(meta['id'])
            if not fresh or any(fresh.get(k) != meta.get(k) for k in ('id','rev','content_hash','path_display')): raise ValueError('Source changed before master registration. Review it and retry.')
            service.register(product)
            existing = service.mappings.read().get(pid)
            if existing and existing['dropbox_file_id'] != meta['id']: raise ValueError('Product mapping changed. Use the established replacement workflow.')
            if not existing: service.mappings.attach(pid,meta,row['data']['lifecycle']['actor'],confirm_mismatch=True)
            with connect() as conn, conn.cursor() as cur:
                cur.execute('UPDATE product_psd_mappings SET file_path=%s,updated_at=now() WHERE shopify_product_gid=%s AND dropbox_file_id=%s', (meta['path_display'],pid,meta['id']))
            service.queue.enqueue(pid,meta['id'],str(actor))
            with store.locked(key,actor) as (current,cur):current['data']['lifecycle'].update(state='Complete',reason='',checked_at=now())
        except Exception as error:
            with store.locked(key,actor) as (current,cur):
                current['data']['lifecycle'].update(state='Error',reason=str(error) if isinstance(error,ValueError) else 'Master registration incomplete. Retry file handoff; the confirmed Shopify product is retained.',checked_at=now())
    return True
