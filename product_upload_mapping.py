"""Resumable upload -> existing Shopify product -> Edition Ops registration.

Sync & Map reuses catalogue registration and authoritative PSD mapping.
Only an explicit click starts work. No Shopify writes or preparation admission.
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
            r.next_edition_number AS run_next,r.status AS run_status,r.shopify_product_id AS run_shopify_id
            FROM edition_products p LEFT JOIN edition_runs r ON r.id=p.active_edition_run_id
            AND r.edition_product_id=p.id
            WHERE p.shopify_product_gid=%s OR p.shopify_product_id=%s''', (pid, pid))
        rows = cur.fetchall()
    if len(rows) > 1:
        raise ValueError('Conflicting Edition Ops product identities; review the existing records.')
    if rows and any(rows[0].get(field) and str(rows[0][field]) not in (pid, pid.rsplit('/',1)[-1])
                    for field in ('shopify_product_gid','shopify_product_id','run_shopify_id')):
        raise ValueError('Conflicting Shopify identity on the Edition Ops record or edition run.')
    return dict(rows[0]) if rows else None


def register_edition(connect, product, total):
    """Canonical locked plan/allocator, restricted to exact stable identity.

    Existing counters/runs are never rewritten. Display fields use the canonical
    safe refresh plan. The canonical initializer
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
        source = (op.get('sync_map') or {}).get('moved') or op.get('source') or {}
        if (op.get('product_id') == pid and op.get('binding') in ('correlation', 'existing_mapping', 'operator')
                and all(source.get(k) == metadata.get(k) for k in ('id', 'rev', 'content_hash', 'path_display'))):
            return True
    return False


class Mapping:
    def __init__(self, connect, provider, *, shopify=None, mappings=None, register=None):
        import shopify_sync
        from psd_mapping_store import PostgresMappings
        self.connect, self.store, self.provider = connect, Intakes(connect), provider
        self.shopify = shopify or shopify_sync
        self.mappings = mappings or PostgresMappings(connect)
        self.register = register or (lambda p, n: register_edition(connect, p, n))
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
                if (exact_tag in tags(item) if exact_tag else item.get('status') in ('DRAFT', 'ACTIVE')):
                    result[item['shopify_product_id']] = item
            if not page['has_next_page']:
                return list(result.values())
            next_cursor = page.get('end_cursor')
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        raise ValueError('Catalogue lookup was incomplete. Narrow the product search and retry; nothing was linked.')

    def _guard(self, key, actor, lease):
        """Fence side effects under the durable intake lock, including expired leases.

        A takeover waits for an in-flight mutation. A late reader must prove its
        lease again before it can mutate anything. No process-local lock is authority.
        """
        from contextlib import contextmanager
        from product_upload_source import current_source
        @contextmanager
        def locked():
            with self.store.locked(key, actor['id'], provider_io=True) as (row, cur):
                op = operation(row)
                task = op['sync_map']
                if task.get('lease') != lease:
                    raise ValueError('Another attempt owns Sync & Map. Refresh its progress.')
                current_source(row, task['source_version'])
                if row['mode'] != task['mode']:
                    raise ValueError('The upload mode changed. Retry with the current saved operation.')
                task['lease_until'] = (now()+timedelta(minutes=5)).isoformat()
                yield row, op, task, cur
        return locked()

    def _step(self, key, actor, lease, stage, **values):
        with self._guard(key, actor, lease) as (row, op, task, cur):
            task.update(stage=stage, **values)

    def _identity(self, key, row):
        op = operation(row)
        pid = op.get('product_id') or row['data'].get('product_gid')
        marker = tag(key)
        matches = self.catalogue('tag:"'+marker+'"', exact_tag=marker)
        if len(matches) > 1:
            raise ValueError('Multiple Shopify products have this upload correlation tag. Resolve the conflict; no product was chosen.')
        if not matches:
            raise ValueError('Product not found in Shopify yet')
        found = matches[0]['shopify_product_id']
        if pid and pid != found:
            raise ValueError('The saved Shopify product ID conflicts with this upload correlation tag.')
        product = self.shopify.fetch_product_by_shopify_id(pid or found)
        if not product or product.get('shopify_product_id') != found or marker not in tags(product):
            raise ValueError('Shopify identity or correlation changed during verification. Retry after resolving the conflict.')
        status = product.get('status')
        if status not in ('DRAFT', 'ACTIVE'):
            raise ValueError('The Shopify product is archived or unavailable.')
        if row['mode'] == 'DRAFT' and status != 'DRAFT':
            raise ValueError('This upload expects a Shopify draft. Its publication state was not changed.')
        if row['mode'] == 'LIVE' and (status != 'ACTIVE' or not product.get('online_store_url')):
            raise ValueError('The requested Shopify live publication is not confirmed yet.')
        return product

    def _mapping_conflicts(self, pid, source):
        # Existing authority, including the one-product-per-file constraint.
        existing = self.mappings.read()
        if pid in existing and existing[pid]['dropbox_file_id'] != source['id']:
            raise ValueError('This product already maps to another PSD. Nothing was replaced.')
        if any(m['dropbox_file_id'] == source['id'] and p != pid for p,m in existing.items()):
            raise ValueError('This PSD already maps to a different Shopify product. Nothing was replaced.')
        return existing.get(pid)

    @staticmethod
    def _edition(edition, task):
        if (not edition or not edition.get('id') or not edition.get('run_id') or
                not edition.get('active') or not edition.get('is_active') or edition['run_status'] != 'active' or
                edition['run_total'] != edition['edition_total'] or edition['run_next'] != edition['next_edition_number']):
            raise ValueError('Edition setup needs review: a consistent active run is required. No existing history was reset or reopened.')
        if any(task.get(k) and task[k] != edition[field] for k,field in [('edition_id','id'),('run_id','run_id')]):
            raise ValueError('The Edition Ops record or run changed during mapping. Resolve the conflict before retrying.')
        return edition

    def _move(self, key, actor, lease, product):
        from product_upload_dropbox import verify_roots, within
        from product_upload_lifecycle import filename
        from product_upload_mapping_hold import verify
        roots = verify_roots(self.provider)
        with self._guard(key, actor, lease) as (row, op, task, cur):
            source = op['source']
            verify(cur, key, product['shopify_product_id'], source['id'])
            live_path = roots['live']['path']
            # Preserve a pre-existing master name; Review masters use the existing
            # title sanitisation convention. The intent never changes on retry.
            target = (source['path_display'] if source['path_display'].rsplit('/',1)[0].casefold() == live_path.casefold()
                      else live_path+'/'+filename(product['title']))
            task.setdefault('move_intent', dict(source=deepcopy(source), to=target, folder=roots['live']))
            if task['move_intent']['folder'] != roots['live']:
                raise ValueError('The configured live-designs destination changed. Review the saved move intent.')
        # Intent committed BEFORE provider mutation: lost responses reconcile by ID.
        with self._guard(key, actor, lease) as (row, op, task, cur):
            source = op['source']; intent = task['move_intent']; target = intent['to']
            current = self.provider.metadata_if_present(source['id'])
            expected = task.get('moved') or source
            recovered = bool(current and not task.get('moved') and source['path_display'] != target and current.get('path_display') == target
                             and current.get('id') == source['id'] and current.get('content_hash') == source['content_hash']
                             and current.get('size') == source.get('size'))
            if not current or (not recovered and any(current.get(k) != expected.get(k) for k in ('id','rev','content_hash','path_display','size'))):
                raise ValueError('The original PSD source revision changed. No replacement was moved.')
            if current['path_display'] != target and not within(current['path_display'], roots['review']['path']):
                raise ValueError('The original PSD is outside the configured Review source.')
            occupied = self.provider.metadata_if_present(target)
            if occupied and occupied.get('id') != source['id']:
                raise ValueError('Destination conflict: another design occupies the live path. Nothing was overwritten.')
            if current['path_display'] != target:
                # Recheck preparation exclusion immediately before the move.
                verify(cur, key, product['shopify_product_id'], source['id'])
                self.provider.api.move_path(self.provider.token, source['id'], target, root_path=self.provider.context['root_path'])
            fresh = self.provider.metadata_if_present(source['id'])
            if (not fresh or fresh.get('path_display') != target or not fresh.get('rev') or
                    any(fresh.get(k) != source.get(k) for k in ('id','content_hash','size'))):
                raise ValueError('Dropbox did not verify the original PSD at its intended destination. Retry to reconcile the saved move.')
            task['moved'] = deepcopy(fresh)
            return fresh

    def map(self, key, actor, *, product_id=None, confirmed_limit=None, source_version=None):
        import os_accounts
        from time import monotonic
        from product_upload_source import current_source
        from product_upload_mapping_hold import acquire, verify
        if not os_accounts.can_attach_missing_psd(actor):
            raise PermissionError('Your account needs permission to attach a product PSD.')
        lease = str(uuid.uuid4()); started = monotonic()
        with self.store.locked(key, actor['id']) as (row, cur):
            source = current_source(row, source_version)
            op = operation(row); task = op.setdefault('sync_map', {})
            if row['data'].get('lifecycle'):
                raise ValueError('This older upload has an existing Companion handoff. Review that retained workflow before Sync & Map; it was not changed.')
            if row['data'].get('workflow_version') != 3:
                raise ValueError('Sync & Map requires the current Dropbox PSD selection workflow.')
            if task.get('lease_until') and datetime.fromisoformat(task['lease_until']) > now():
                return self._status_row(row)
            task.update(lease=lease, lease_until=(now()+timedelta(minutes=5)).isoformat(), state='Mapping…', error='',
                        stage='Finding Shopify product', source_version=source['version'], mode=row['mode'], needs_limit=False)
            task.setdefault('completed', [])
            captured = deepcopy(row)
        stage = 'Finding Shopify product'; phase = monotonic()
        def step(next_stage):
            nonlocal stage, phase
            with self._guard(key, actor, lease) as (row, op, task, cur):
                task.setdefault('timings_ms', {})[stage] = round((monotonic()-phase)*1000, 2)
                if stage not in task['completed']: task['completed'].append(stage)
                task['stage'] = next_stage
            stage, phase = next_stage, monotonic()
        try:
            product = self._identity(key, captured); pid = product['shopify_product_id']
            if product_id and product_id != pid:
                raise ValueError('A supplied product ID conflicts with the exact upload correlation.')
            original = operation(captured)['source']
            self._mapping_conflicts(pid, original)
            # Reject a changed initial source before registration or any movement.
            if not captured['data']['upload_operation']['sync_map'].get('move_intent'):
                self.source(captured)
            with self._guard(key, actor, lease) as (row, op, task, cur):
                op.update(product_id=pid, binding='correlation', product=summary(product))
                row['data'].update(product_gid=pid, product_title=product['title'], product_url=product.get('admin_url',''))
            acquire(self.connect, key, actor['id'], pid, original['id'])
            step('Syncing Edition Ops')
            edition = read_edition(self.connect, pid)
            limit = edition['edition_total'] if edition else edition_limit(product, confirmed_limit if confirmed_limit is not None else captured['data']['upload_operation']['sync_map'].get('confirmed_limit'))
            if limit is None:
                self._step(key, actor, lease, 'Checking edition setup', state='Pending sync', needs_limit=True,
                           error='Confirm the edition limit for this new product, then resume Sync & Map.')
                return self.status(key, actor)
            with self._guard(key, actor, lease) as (row, op, task, cur):
                self.register(product, limit)
                task['confirmed_limit'] = limit
            step('Checking edition setup')
            # Fresh read after canonical registration's transaction has committed.
            edition = self._edition(read_edition(self.connect, pid), captured['data']['upload_operation']['sync_map'])
            self._step(key, actor, lease, stage, edition_id=edition['id'], run_id=edition['run_id'])
            step('Moving PSD')
            self._mapping_conflicts(pid, original)
            moved = self._move(key, actor, lease, product)
            step('Saving mapping')
            with self._guard(key, actor, lease) as (row, op, task, cur):
                self._edition(read_edition(self.connect, pid), task)
                verify(cur, key, pid, moved['id'])
                self.mappings.attach(pid, moved, actor, confirm_mismatch=True, upload_operation=key)
            step('Verifying')
            # Fresh exact reads, not cached list entries or submission acknowledgements.
            self._identity(key, self.store.read(key, actor['id']))
            fresh = self.provider.metadata_if_present(moved['id'])
            if not fresh or any(fresh.get(k) != moved.get(k) for k in ('id','rev','content_hash','path_display','size')):
                raise ValueError('The PSD changed after moving. Mapping success cannot be confirmed.')
            with self._guard(key, actor, lease) as (row, op, task, cur):
                self._verify_database(cur, key, op, task)
                task.update(state='Mapped', error='', verified_at=now().isoformat(), preparation_held=True,
                            elapsed_ms=round((monotonic()-started)*1000,2))
                if stage not in task['completed']: task['completed'].append(stage)
                task.setdefault('timings_ms', {})[stage] = round((monotonic()-phase)*1000,2)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Upload Sync & Map failed: operation=%s stage=%s', key, stage)
            message = str(error) if isinstance(error,(ValueError,PermissionError)) else 'Service unavailable. Retry this step; completed steps and the original PSD identity are retained.'
            with self.store.locked(key, actor['id']) as (row, cur):
                task = operation(row).get('sync_map', {})
                if task.get('lease') == lease:
                    task.update(state='Pending sync' if message=='Product not found in Shopify yet' else 'Mapping failed',
                                error=message, stage=stage, elapsed_ms=round((monotonic()-started)*1000,2))
        finally:
            with self.store.locked(key, actor['id']) as (row, cur):
                task = operation(row).get('sync_map', {})
                if task.get('lease') == lease: task['lease_until'] = None
        return self.status(key, actor)

    def _verify_database(self, cur, key, op, task):
        from product_upload_mapping_hold import verify
        pid = op['product_id']; meta = task['moved']
        verify(cur, key, pid, meta['id'])
        edition = self._edition(read_edition(self.connect, pid), task)
        mapping = self.mappings.read_one(pid)
        if not mapping or mapping['dropbox_file_id'] != meta['id'] or mapping['file_path'] != meta['path_display']:
            raise ValueError('The authoritative PSD mapping does not match the verified destination.')
        return edition

    def _status_row(self, row):
        op = row['data'].get('upload_operation') or {}; task = op.get('sync_map') or {}
        result = dict(state=task.get('state','Unmapped'), reason=task.get('error',''), stage=task.get('stage',''),
                      completed=task.get('completed',[]), needs_limit=task.get('needs_limit',False), product=op.get('product'),
                      psd=(task.get('moved') or op.get('source') or {}).get('path_display',''),
                      edition_id=task.get('edition_id'), run_id=task.get('run_id'), edition_limit=task.get('confirmed_limit'),
                      preparation_held=task.get('preparation_held',False), elapsed_ms=task.get('elapsed_ms'),
                      timings_ms=task.get('timings_ms',{}))
        if result['state']=='Mapping…' and (not task.get('lease_until') or datetime.fromisoformat(task['lease_until'])<=now()):
            result.update(state='Pending sync',reason='Sync & Map was interrupted. Retry to resume its saved steps.')
        return result

    def status(self, key, actor):
        """Small DB reads only: polling must never contact Shopify or Dropbox."""
        try:
            from product_upload_source import current_source
            row = self.store.read(key, actor['id'])
            if not row: raise ValueError('Saved upload unavailable to this account.')
            op = row['data'].get('upload_operation') or {}; task = op.get('sync_map') or {}
            if task:
                current_source(row, task.get('source_version'))
                if task.get('mode') != row['mode']: raise ValueError('Upload mode changed. Retry Sync & Map.')
            result = self._status_row(row)
            if result['state']=='Mapped':
                with self.connect() as conn, conn.cursor() as cur:
                    self._verify_database(cur,key,op,task)
                result['reason'] = 'Success — synced and PSD mapped'
            return result
        except Exception as error:
            return dict(state='Status unavailable', reason=str(error) if isinstance(error,ValueError) else
                        'Could not verify saved mapping status. Retry Sync & Map; no mapping was changed.')
