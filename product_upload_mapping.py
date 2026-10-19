"""Resumable upload -> existing Shopify product -> Edition Ops registration.

GET status is read-only. MAP never creates/publishes a product, moves a PSD,
allocates an edition, or releases an order. Provider calls are outside intake locks.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re
import uuid

from product_upload_identity import operation, tag
from product_upload_intake import Intakes


def now():
    return datetime.now(timezone.utc)


def summary(product):
    return dict(id=product['shopify_product_id'], title=product['title'], handle=product.get('handle', ''),
                thumbnail=product.get('thumbnail_url') or next((i['url'] for i in product.get('images', []) if i.get('url')), ''),
                status=product.get('status', ''))


def tags(product):
    value = product.get('tags') or []
    return value.split(',') if isinstance(value, str) else value


def edition_limit(product, confirmed=None):
    values = {int(t.removeprefix('sc-edition-limit-')) for t in tags(product)
              if re.fullmatch(r'sc-edition-limit-[1-9][0-9]*', t)}
    for field in product.get('metafields', []):
        if field.get('namespace') == 'sports_cave' and field.get('key') == 'edition_total':
            if not re.fullmatch(r'[1-9][0-9]*', str(field.get('value', ''))):
                raise ValueError('Shopify edition limit is invalid; review Edition Ops.')
            values.add(int(field['value']))
    if confirmed is not None:
        if type(confirmed) is not int or not 1 <= confirmed <= 1000:
            raise ValueError('Confirm an edition limit between 1 and 1000.')
        values.add(confirmed)
    if len(values) > 1:
        raise ValueError('Conflicting edition limits. Review the product before mapping.')
    if not values:
        return None
    value = values.pop()
    if not 1 <= value <= 1000:
        raise ValueError('The edition limit is outside the supported range.')
    return value


def read_edition(connect, pid):
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT p.*,r.id AS run_id,r.edition_total AS run_total,
            r.next_edition_number AS run_next,r.status AS run_status
            FROM edition_products p LEFT JOIN edition_runs r ON r.id=p.active_edition_run_id
            AND r.edition_product_id=p.id
            WHERE p.shopify_product_gid=%s OR p.shopify_product_id=%s''', (pid, pid))
        rows = cur.fetchall()
    if len(rows) > 1:
        raise ValueError('Conflicting Edition Ops product identities; review the existing records.')
    return dict(rows[0]) if rows else None


def register_edition(connect, product, total):
    """Canonical locked plan/allocator, restricted to exact stable identity.

    Existing records/runs/counters are never rewritten. The canonical initializer
    checks orphaned orders/runs/tombstones and creates a run without allocating.
    """
    import supabase_backend as db
    import shopify_sync
    if product.get('status') not in ('DRAFT', 'ACTIVE'):
        raise ValueError('The product is archived or unavailable.')
    probe = dict(product, status='ACTIVE', online_store_url='upload-registration')
    if not shopify_sync.edition_registration_eligibility(probe)['eligible']:
        raise ValueError('This product is not eligible Sports Cave Framed Art. Review its vendor, type and exclusions.')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
        existing = db._candidate_edition_products_for_shopify_products(cur, [product])
        actions = db._plan_edition_product_incremental_sync([product], existing, include_intake_drafts=True, upload_mapping=True)
        for action in actions:
            if action['action'] in ('skip', 'update'):
                if action.get('match_type') != 'shopify_product_id':
                    raise ValueError('Legacy edition history needs explicit stable-ID reconciliation in Edition Ops.')
                action['action'] = 'skip'
            if action['action'] == 'insert':
                if total is None:
                    raise ValueError('Confirm the edition limit before creating a new edition run.')
                action['fields']['_upload_confirmed_total'] = total
        # Cache the refreshed Shopify record without changing publication state.
        db._upsert_shopify_product_display_row(cur, product)
        result = db._apply_edition_product_incremental_plan(cur, actions, sync_variants=False)
        if result['errors']:
            raise ValueError('; '.join(result['errors']))


def approved_upload_source(connect, pid, metadata, *, actor=None, key=None):
    """Narrow Review-folder exception, backed by the exact persisted operation.

    Standalone mapping and reset folder policies remain unchanged.
    """
    from product_upload_dropbox import approved, REVIEW
    import psd_directory
    if not approved(metadata) or not (psd_directory.approved_file(metadata) or metadata.get('path_display','').rsplit('/',1)[0] == REVIEW):
        return False
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id,actor_id,data FROM product_upload_intakes WHERE data->>'product_gid'=%s", (pid,))
        rows = cur.fetchall()
    for row in rows:
        if key and str(row['id']) != str(key) or actor and row['actor_id'] != str(actor):
            continue
        op = row['data'].get('upload_operation') or {}
        source = op.get('source') or {}
        if (op.get('product_id') == pid and op.get('binding') in ('correlation', 'existing_mapping', 'operator')
                and all(source.get(k) == metadata.get(k) for k in ('id', 'rev', 'content_hash', 'path_display'))):
            return True
    return False


class Mapping:
    def __init__(self, connect, provider, *, shopify=None, mappings=None, queue=None, register=None, mirror=None):
        import shopify_sync
        from psd_mapping_store import PostgresMappings
        from auto_editions_onboarding_store import Queue
        self.connect, self.store, self.provider = connect, Intakes(connect), provider
        self.shopify = shopify or shopify_sync
        self.mappings = mappings or PostgresMappings(connect)
        self.queue = queue or Queue(connect)
        self.register = register or (lambda p, n: register_edition(connect, p, n))
        self.mirror = mirror or self._mirror

    def _mirror(self, product):
        import supabase_backend as db
        edition = read_edition(self.connect, product['shopify_product_id'])
        if edition.get('metafields_sync_status') == 'Pending automatic mirror':
            db._mirror_pending_registered_product(product['shopify_product_id'])
        else:
            db.sync_product_edition_metafields(edition['shopify_handle'], ensure_schema_first=False)

    def source(self, row):
        op = operation(row)
        meta = self.provider.metadata_if_present(op['source']['id'])
        if not meta or any(meta.get(k) != op['source'].get(k) for k in ('id', 'rev', 'content_hash', 'path_display')):
            raise ValueError('The captured PSD changed or is inaccessible. Restore that revision or start a new upload; no replacement was made.')
        return meta

    def catalogue(self, query, *, exact_tag=None):
        result, cursor = {}, None
        for _ in range(10):
            page = self.shopify.fetch_catalog_page(search=query, after=cursor, page_size=100)
            for item in page['products']:
                if item.get('status') in ('DRAFT', 'ACTIVE') and (not exact_tag or exact_tag in tags(item)):
                    result[item['shopify_product_id']] = item
            if not page['has_next_page']:
                return list(result.values())
            next_cursor = page.get('end_cursor')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        raise ValueError('Catalogue lookup was incomplete. Narrow the product search and retry; nothing was linked.')

    def candidates(self, key, actor, search=''):
        row = self.store.read(key, actor['id'])
        if not row:
            raise ValueError('This saved upload is unavailable.')
        # Discovery suggestions are NEVER evidence for automatic binding.
        value = str(search or (row['data'].get('mockups_context') or {}).get('design_name') or '').strip()[:180]
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        query = '(status:active OR status:draft)'
        if value.startswith('gid://shopify/Product/'):
            products = [self.shopify.fetch_product_by_shopify_id(value)]
        else:
            query += (' AND (handle:"' + escaped + '*" OR title:"' + escaped.replace('-', ' ') + '*")') if value else ''
            products = self.catalogue(query)[:50]
        choices = [summary(p) for p in products if p.get('status') in ('DRAFT', 'ACTIVE')]
        with self.store.locked(key, actor['id']) as (current, cur):
            operation(current)
            current['data']['mapping_candidates'] = choices
        return choices

    def _checkpoint(self, key, actor, lease, **values):
        with self.store.locked(key, actor['id']) as (row, cur):
            op = operation(row)
            if op.get('lease') != lease:
                raise ValueError('Another mapping attempt owns this operation. Refresh status.')
            op.update(values)

    def register_worker(self, pid, meta, actor):
        """Queue and pin the captured revision in one transaction, without reset."""
        import auto_editions as ae
        import json
        source = ae.source_identity(pid, meta)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
            self.queue.enqueue_cursor(cur, pid, meta['id'], str(actor['id']), expected_source=source)
            cur.execute('SELECT file_id,source FROM auto_edition_onboarding WHERE product_gid=%s FOR UPDATE', (pid,))
            worker = cur.fetchone()
            if not worker or worker['file_id'] != meta['id'] or worker['source'] and worker['source'] != source:
                raise ValueError('Worker preparation belongs to another PSD revision. Review its existing checkpoint; it was not reset.')
            if worker['source'] is None:
                cur.execute('UPDATE auto_edition_onboarding SET source=%s::jsonb WHERE product_gid=%s', (json.dumps(source), pid))
                self.queue.audit(cur, pid, str(actor['id']), 'upload_source_pinned', source)

    def map(self, key, actor, *, product_id=None, confirmed_limit=None):
        import os_accounts
        if not os_accounts.can_attach_missing_psd(actor):
            raise PermissionError('Your account needs permission to attach a product PSD.')
        lease = str(uuid.uuid4())
        with self.store.locked(key, actor['id']) as (row, cur):
            if not row['data'].get('mockups_exported'):
                raise ValueError('Save this upload’s prepared images before mapping.')
            op = operation(row)
            if op.get('lease_until') and datetime.fromisoformat(op['lease_until']) > now():
                return dict(state='Mapping…', reason='The existing mapping attempt is still running.')
            op.update(lease=lease, lease_until=(now()+timedelta(minutes=5)).isoformat(), state='Mapping…', error='')
            captured = deepcopy(row)
        stage = 'Resolving product'
        try:
            meta = self.source(captured)
            op = captured['data']['upload_operation']
            bound_pid = captured['data'].get('product_gid') or op.get('product_id')
            pid = bound_pid
            binding = op.get('binding')
            if product_id and pid and product_id != pid:
                raise ValueError('This operation is already bound to another product; its saved identity cannot be replaced.')
            if not pid and product_id:
                if product_id not in {p['id'] for p in captured['data'].get('mapping_candidates', [])}:
                    raise ValueError('Choose a product from this upload’s current selector.')
                pid, binding = product_id, 'operator'
            if not pid:
                marker = tag(key)
                matches = self.catalogue('tag:"' + marker + '" AND (status:active OR status:draft)', exact_tag=marker)
                if len(matches) == 1:
                    pid, binding = matches[0]['shopify_product_id'], 'correlation'
                elif not matches and not op.get('correlation_expected'):
                    # Legacy recovery only. A newly correlated upload may reuse
                    # an old PSD but create a different product; the PSD alone
                    # must never redirect that operation to the older product.
                    existing = [p for p,m in self.mappings.read().items() if m['dropbox_file_id'] == meta['id']]
                    if len(existing) == 1:
                        pid, binding = existing[0], 'existing_mapping'
                    elif len(existing) > 1:
                        raise ValueError('Multiple products are linked to this PSD. Resolve the conflict in Edition Ops.')
                if not pid:
                    self._checkpoint(key, actor, lease, state='Pending sync',
                        error='More than one product has this operation tag. Select the intended product explicitly.' if matches else
                              'Waiting for the correlated Shopify product. Retry shortly, or select an existing product for a legacy upload.')
                    return self.status(key, actor)
            product = self.shopify.fetch_product_by_shopify_id(pid)
            if product.get('shopify_product_id') != pid or product.get('status') not in ('DRAFT', 'ACTIVE'):
                raise ValueError('The confirmed Shopify product is unavailable or archived.')
            if not bound_pid and binding == 'correlation' and tag(key) not in tags(product):
                raise ValueError('Shopify correlation changed during lookup. Refresh and retry.')
            with self.store.locked(key, actor['id']) as (row, cur):
                saved = operation(row)
                if saved.get('lease') != lease:
                    raise ValueError('Mapping ownership changed; refresh status.')
                cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('product-file-link:'+meta['id'],))
                cur.execute("SELECT id FROM product_upload_intakes WHERE data->'source'->>'id'=%s AND data->>'product_gid' IS NOT NULL AND data->>'product_gid'<>%s LIMIT 1", (meta['id'], pid))
                if cur.fetchone():
                    raise ValueError('The exact PSD is already linked to a different Shopify product.')
                row['data'].update(product_gid=pid, product_title=product['title'], product_url=product.get('admin_url', ''))
                saved.update(product_id=pid, product_handle=product.get('handle'), binding=binding or 'existing_mapping',
                             product=summary(product))
                saved.setdefault('output', deepcopy(row['data'].get('mockups_context')))
                saved.setdefault('mapped_output', deepcopy(saved['output']))
            existing_mapping = self.mappings.read().get(pid)
            if existing_mapping and existing_mapping['dropbox_file_id'] != meta['id']:
                raise ValueError('This product already maps to another PSD. Use Edition Ops replacement; nothing was overwritten.')
            stage = 'Edition Ops'
            edition = read_edition(self.connect, pid)
            limit = edition_limit(product, confirmed_limit if confirmed_limit is not None else op.get('confirmed_limit')) if not edition else edition['edition_total']
            if limit is None:
                self._checkpoint(key, actor, lease, state='Pending sync', needs_limit=True,
                                 error='Confirm the edition limit shown on the product before initialising its run.')
                return self.status(key, actor)
            self._checkpoint(key, actor, lease, confirmed_limit=limit)
            self.register(product, limit)
            edition = read_edition(self.connect, pid)
            if not edition or not edition.get('run_id'):
                raise ValueError('The existing edition record has no valid run. Review Edition Ops; no history was reset.')
            self._checkpoint(key, actor, lease, edition_id=edition['id'], run_id=edition['run_id'], needs_limit=False)
            stage = 'PSD mapping'
            if not existing_mapping:
                self.mappings.attach(pid, meta, actor, confirm_mismatch=True, upload_operation=key)
            self._checkpoint(key, actor, lease, mapping_saved=True)
            stage = 'Shopify sync'
            current = self.status(key, actor)
            if not current.get('sync_verified'):
                self.mirror(product)
            stage = 'Worker registration'
            self.register_worker(pid, meta, actor)
            self._checkpoint(key, actor, lease, worker_registered=True, state='Pending sync', error='')
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Upload mapping failed: operation=%s stage=%s', key, stage)
            message = str(error) if isinstance(error, (ValueError, PermissionError)) else 'Service unavailable. Retry the failed step; the saved product and PSD identities are retained.'
            self._checkpoint(key, actor, lease, state='Pending sync' if stage in ('Shopify sync', 'Worker registration') else 'Mapping failed', error=stage+': '+message)
        finally:
            self._checkpoint(key, actor, lease, lease_until=None)
        result = self.status(key, actor)
        if result['state'] == 'Mapped':
            with self.store.locked(key, actor['id']) as (row, cur):
                saved = operation(row)
                if saved.get('lease') == lease:
                    saved.update(state='Mapped', error='', worker_registered=True, sync_verified=True,
                                 verified_at=now().isoformat())
        return result

    def status(self, key, actor):
        """Read authoritative state only; never enqueue, sync, or map on refresh."""
        try:
            row = self.store.read(key, actor['id'])
            if not row:
                raise ValueError('Saved upload unavailable to this account.')
            op = row['data'].get('upload_operation') or {}
            pid = row['data'].get('product_gid') or op.get('product_id')
            result = dict(state=op.get('state', 'Unmapped'), reason=op.get('error', ''),
                          psd=(op.get('source') or row['data'].get('source') or {}).get('name', ''),
                          needs_limit=op.get('needs_limit', False), product=op.get('product'), worker='Not registered')
            if result['state'] == 'Mapping…' and (not op.get('lease_until') or datetime.fromisoformat(op['lease_until']) <= now()):
                result.update(state='Pending sync', reason='The mapping attempt was interrupted. Retry MAP to resume its saved steps.')
            if not pid:
                return result
            product = self.shopify.fetch_product_by_shopify_id(pid)
            if product.get('shopify_product_id') != pid or product.get('status') not in ('DRAFT', 'ACTIVE'):
                raise ValueError('The saved Shopify product is unavailable or archived.')
            result['product'] = summary(product)
            meta = self.source(row)
            edition = read_edition(self.connect, pid)
            mapping = self.mappings.read().get(pid)
            with self.connect() as conn, conn.cursor() as cur:
                cur.execute('SELECT product_gid,file_id,status,source FROM auto_edition_onboarding WHERE product_gid=%s', (pid,))
                worker = cur.fetchone()
            result.update(edition_limit=edition.get('edition_total') if edition else None,
                          next_edition=f"{edition['next_edition_number']:03d}" if edition else None,
                          worker=worker['status'] if worker and worker['file_id'] == meta['id'] else 'Not registered')
            values = {m['key']: str(m['value']).lower() for m in product.get('metafields', []) if m.get('namespace') == 'sports_cave'}
            configured = bool(edition and edition.get('run_id') and edition.get('active') and edition.get('is_active')
                              and edition['run_status'] == 'active' and edition['run_total'] == edition['edition_total']
                              and edition['run_next'] == edition['next_edition_number'])
            expected = ({'edition_total': str(edition['edition_total']), 'edition_next_number': str(edition['next_edition_number']),
                         'edition_sold_count': str(edition['sold_count']), 'edition_remaining': str(edition['remaining_count']),
                         'edition_enabled': 'true', 'edition_status': str(edition['edition_status']).lower(),
                         'edition_label': str(edition['edition_name']).lower()} if edition else {})
            synced = bool(configured and edition.get('metafields_sync_status') == 'Synced'
                          and all(values.get(k) == v for k,v in expected.items()))
            result['sync_verified'] = synced
            import auto_editions as ae
            worker_ok = bool(worker and worker['file_id'] == meta['id'] and
                             worker['source'] == ae.source_identity(pid, meta))
            linked = bool(mapping and mapping['dropbox_file_id'] == meta['id'])
            if linked and configured and synced and worker_ok:
                result.update(state='Mapped', reason='Product, exact PSD, edition run, Shopify sync and worker registration verified.')
            elif result['state'] != 'Mapping failed':
                result['state'] = 'Pending sync'
                if not result['reason']:
                    result['reason'] = ('Edition run configuration needs review.' if not configured else
                                        'PSD linkage is incomplete.' if not linked else
                                        'Shopify edition sync is not yet verified.' if not synced else 'Worker registration is incomplete; retry MAP.')
            return result
        except Exception as error:
            return dict(state='Status unavailable', reason=str(error) if isinstance(error, ValueError) else
                        'Could not verify saved mapping status. Check service access and refresh status; no mapping was changed.')
