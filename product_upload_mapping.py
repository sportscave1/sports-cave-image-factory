"""Resumable upload -> existing Shopify product -> Edition Ops registration.

Map reads webhook registration and reuses authoritative PSD mapping.
Only an explicit click starts work. Preparation follows verified finalisation.
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
            WHERE p.shopify_product_gid=%s OR p.shopify_product_id=ANY(%s)''', (pid, [pid,pid.rsplit('/',1)[-1]]))
        rows = cur.fetchall()
    if len(rows) > 1:
        raise ValueError('Conflicting Edition Ops product identities; review the existing records.')
    if rows and any(rows[0].get(field) and str(rows[0][field]) not in (pid, pid.rsplit('/',1)[-1])
                    for field in ('shopify_product_gid','shopify_product_id','run_shopify_id')):
        raise ValueError('Conflicting Shopify identity on the Edition Ops record or edition run.')
    if not rows:
        return None
    edition = dict(rows[0])
    # Psycopg returns production UUID run IDs as UUID objects. Mapping receipts
    # are JSON; retain the exact ID as text, including on subsequent comparisons.
    if isinstance(edition.get('run_id'), uuid.UUID):
        edition['run_id'] = str(edition['run_id'])
    return edition


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
        if (op.get('sync_map') or {}).get('manual_takeover'):
            continue
        source = (op.get('sync_map') or {}).get('moved') or op.get('source') or {}
        if (op.get('product_id') == pid and op.get('binding') in ('correlation', 'existing_mapping', 'operator')
                and all(source.get(k) == metadata.get(k) for k in ('id', 'rev', 'content_hash', 'path_display'))):
            return True
    return False


class Mapping:
    def __init__(self, connect, provider, *, shopify=None, mappings=None, register=None, onboard=None, shop_domain=None):
        import shopify_sync
        from psd_mapping_store import PostgresMappings
        self.connect, self.store, self.provider = connect, Intakes(connect), provider
        self.shopify = shopify or shopify_sync
        self.mappings = mappings or PostgresMappings(connect)
        self.register = register or (lambda p, n: register_edition(connect, p, n))  # legacy callers only
        self.shop_domain = shopify_sync.normalize_store_domain(shop_domain or self.shopify.get_config()['store_domain'])
        self.onboard = onboard  # Retained constructor compatibility; MAP never starts sync.
    def source(self, row):
        op = operation(row)
        meta = self.provider.metadata_if_present(op['source']['id'])
        if not meta or any(meta.get(k) != op['source'].get(k) for k in ('id', 'rev', 'content_hash', 'path_display')):
            raise ValueError('The captured PSD changed or is inaccessible. Restore that revision or start a new upload; no replacement was made.')
        return meta

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
                if task.get('manual_takeover'):
                    raise ValueError('This attempt was retired by manual PSD mapping. Use the Edition Ops link.')
                if task.get('lease') != lease:
                    raise ValueError('Another attempt owns Map. Refresh its progress.')
                current_source(row, task['source_version'])
                if row['mode'] != task['mode']:
                    raise ValueError('The upload mode changed. Retry with the current saved operation.')
                task['lease_until'] = (now()+timedelta(minutes=5)).isoformat()
                yield row, op, task, cur
        return locked()

    def _step(self, key, actor, lease, stage, **values):
        with self._guard(key, actor, lease) as (row, op, task, cur):
            task.update(stage=stage, **values)

    def _local_candidates(self, marker):
        """Exact operation tag in webhook-ingested rows; never a title search."""
        import json
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT p.* FROM edition_products p WHERE
                p.raw->'tags' @> %s::jsonb OR
                (jsonb_typeof(p.raw->'tags')='string' AND %s=ANY(regexp_split_to_array(p.raw->>'tags', ',\\s*'))) OR
                EXISTS (SELECT 1 FROM shopify_products s WHERE
                    regexp_replace(COALESCE(NULLIF(s.shopify_product_gid,''),s.shopify_product_id),'^gid://shopify/Product/','') =
                    regexp_replace(COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id),'^gid://shopify/Product/','')
                    AND (s.raw_json->'tags' @> %s::jsonb OR
                         (jsonb_typeof(s.raw_json->'tags')='string' AND %s=ANY(regexp_split_to_array(s.raw_json->>'tags', ',\\s*')))))
                ORDER BY p.id LIMIT 3""", (json.dumps([marker]),marker,json.dumps([marker]),marker))
            return [dict(p) for p in cur.fetchall()]

    def _identity(self, key, row, selected=None, confirmed=False):
        op = operation(row)
        def gid(value):
            value = str(value or '')
            if value.isdigit(): return 'gid://shopify/Product/' + value
            if re.fullmatch(r'gid://shopify/Product/[0-9]+', value): return value
            raise ValueError('The saved local product has no valid Shopify product ID.')
        if op.get('shop_domain') and op['shop_domain'] != self.shop_domain:
            raise ValueError('This upload belongs to a different Shopify shop.')
        pid = op.get('product_id') or row['data'].get('product_gid')
        binding = op.get('binding') or 'correlation'
        # The authoritative file relationship also recognises repeat uploads
        # whose new operation tag is not present on an already mapped product.
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT shopify_product_gid FROM product_psd_mappings WHERE dropbox_file_id=%s', (op['source']['id'],))
            linked = {gid(p['shopify_product_gid']) for p in cur.fetchall()}
        if len(linked)>1 or (pid and linked and gid(pid) not in linked):
            raise ValueError('The saved product and PSD mapping identities conflict. Nothing was changed.')
        if not pid and linked:
            pid = next(iter(linked)); binding = 'existing_mapping'
        if pid:
            pid = gid(pid)
            if selected and gid(selected) != pid:
                raise ValueError('The selected ID conflicts with the saved product association.')
        else:
            matches = self._local_candidates(tag(key))
            ids = {gid(p.get('shopify_product_gid') or p.get('shopify_product_id')) for p in matches}
            if selected and confirmed is True:
                pid = gid(selected)
                if ids and pid not in ids:
                    raise ValueError('Select one of the exact local correlation candidates.')
                binding = 'operator'
            elif len(matches)==1:
                pid = next(iter(ids)); binding = 'correlation'
            else:
                error = ValueError('Confirm the exact Edition Ops product below.' if matches else 'Waiting for product in Edition Ops. Retry lookup after the record arrives, or provide its exact saved product ID.')
                error.candidates = [dict(id=gid(p.get('shopify_product_gid') or p.get('shopify_product_id')), title=p['product_title']) for p in matches]
                raise error
        edition = read_edition(self.connect, pid)
        if not edition:
            error = ValueError('Waiting for product in Edition Ops. Retry lookup after the record arrives. No PSD was moved.')
            error.waiting = True
            raise error
        raw = edition.get('raw') or {}
        return dict(shopify_product_id=pid, title=edition['product_title'],
                    handle=edition.get('shopify_handle',''), thumbnail_url=edition.get('featured_image_url',''),
                    status=raw.get('status',''), admin_url=raw.get('admin_url',''), _upload_binding=binding)

    def _mapping_conflicts(self, pid, source):
        # Existing authority, including the one-product-per-file constraint.
        existing = self.mappings.read()
        if pid in existing and existing[pid]['dropbox_file_id'] != source['id']:
            raise ValueError('This product already maps to another PSD. Nothing was replaced.')
        if any(m['dropbox_file_id'] == source['id'] and p != pid for p,m in existing.items()):
            raise ValueError('This PSD already maps to a different Shopify product. Nothing was replaced.')
        return existing.get(pid)

    def _verify_existing_revision(self, pid, source):
        """Reuse a valid link; never replace a known prepared source revision."""
        import auto_editions as ae
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT source FROM auto_edition_onboarding WHERE product_gid=%s',(pid,))
            prior=cur.fetchone()
            expected=(prior or {}).get('source')
            if not expected:
                cur.execute("SELECT after_state->'source' AS source FROM product_psd_mapping_audit WHERE shopify_product_gid=%s AND jsonb_typeof(after_state->'source')='object' ORDER BY id DESC LIMIT 1",(pid,))
                prior=cur.fetchone()
                if prior:
                    expected=ae.source_identity(pid,prior['source'])
            if not expected:
                cur.execute("SELECT manifest->'source' AS source FROM auto_edition_preparations WHERE manifest->'source'->>'product_gid'=%s ORDER BY created_at DESC LIMIT 1",(pid,))
                expected=(cur.fetchone() or {}).get('source')
            if expected and expected!=ae.source_identity(pid,source):
                raise ValueError('This PSD differs from the existing mapped revision. Use the explicit replacement workflow.')

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
            # Edition Ops display name and existing filename sanitiser. The intent
            # never changes on retry; edition_name is a run label, not this name.
            target = (source['path_display'] if source['path_display'].rsplit('/',1)[0].casefold() == live_path.casefold()
                      else live_path+'/'+filename(task['edition_title']))
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

    def map(self, key, actor, *, product_id=None, confirmed_limit=None, source_version=None, confirm_product=False):
        import os_accounts
        from time import monotonic
        from product_upload_source import current_source
        from product_upload_mapping_hold import acquire, verify
        if not os_accounts.can_attach_missing_psd(actor):
            raise PermissionError('Your account needs permission to attach a product PSD.')
        prior = self.store.read(key, actor['id'])
        prior_task = ((prior or {}).get('data',{}).get('upload_operation') or {}).get('sync_map') or {}
        if prior_task.get('manual_takeover'):
            raise ValueError('This attempt was retired by manual PSD mapping. Use the Edition Ops link.')
        if prior_task.get('state') == 'Mapped':
            current_source(prior, source_version)
            result = self.status(key, actor)
            meta = self.provider.metadata_if_present(prior_task['moved']['id'])
            if result['state']=='Mapped' and meta and all(meta.get(k)==prior_task['moved'].get(k) for k in ('id','rev','content_hash','path_display','size')):
                return result
            raise ValueError('The mapped PSD or edition run changed. Use the existing replacement workflow.')
        lease = str(uuid.uuid4()); started = monotonic()
        with self.store.locked(key, actor['id']) as (row, cur):
            source = current_source(row, source_version)
            op = operation(row); task = op.setdefault('sync_map', {})
            if task.get('manual_takeover'):
                raise ValueError('This attempt was retired by manual PSD mapping. Use the Edition Ops link.')
            if row['data'].get('lifecycle'):
                raise ValueError('This older upload has an existing Companion handoff. Review that retained workflow before Map; it was not changed.')
            if row['data'].get('workflow_version') != 3:
                raise ValueError('Map requires the current Dropbox PSD selection workflow.')
            if task.get('lease_until') and datetime.fromisoformat(task['lease_until']) > now():
                return self._status_row(row)
            task.update(lease=lease, lease_until=(now()+timedelta(minutes=5)).isoformat(), state='Mapping…', error='',
                        stage='Finding product in Edition Ops', source_version=source['version'], mode=row['mode'], needs_limit=False, needs_product=False, candidates=[], resume_upload_id=None)
            task.setdefault('completed', [])
            captured = deepcopy(row)
        stage = 'Finding product in Edition Ops'; phase = monotonic()
        def step(next_stage):
            nonlocal stage, phase
            with self._guard(key, actor, lease) as (row, op, task, cur):
                task.setdefault('timings_ms', {})[stage] = round((monotonic()-phase)*1000, 2)
                if stage not in task['completed']: task['completed'].append(stage)
                task['stage'] = next_stage
            stage, phase = next_stage, monotonic()
        try:
            product = self._identity(key, captured, product_id, confirm_product); pid = product['shopify_product_id']
            if product_id and product_id != pid:
                raise ValueError('A supplied product ID conflicts with the exact upload correlation.')
            original = operation(captured)['source']
            existing=self._mapping_conflicts(pid, original)
            reuse=bool(existing and existing.get('verified') and existing['file_path']==original['path_display'])
            if reuse:self._verify_existing_revision(pid,original)
            # Reject a changed initial source before registration or any movement.
            if not captured['data']['upload_operation']['sync_map'].get('move_intent'):
                self.source(captured)
            with self._guard(key, actor, lease) as (row, op, task, cur):
                op.update(product_id=pid, shop_domain=self.shop_domain, binding=product['_upload_binding'], product=summary(product),
                          publication_binding=dict(shop=self.shop_domain,product_id=pid,source_version=source['version'],source=deepcopy(original)))
                row['data'].update(product_gid=pid, product_title=product['title'], product_url=product.get('admin_url',''))
                task['reused_mapping']=reuse
            step('Linking PSD')
            # Webhooks own registration. A retry only reads their persisted result.
            edition = read_edition(self.connect, pid)
            if not edition:
                error = ValueError('Waiting for product in Edition Ops. Retry lookup after the record arrives. No PSD was moved.')
                error.waiting = True
                raise error
            edition = self._edition(edition, captured['data']['upload_operation']['sync_map'])
            if not (edition.get('product_title') or '').strip():
                raise ValueError('The Edition Ops product name is missing. Correct it before moving the PSD.')
            self._step(key, actor, lease, stage, edition_id=edition['id'], run_id=edition['run_id'],
                       confirmed_limit=edition['edition_total'], edition_title=edition['product_title'])
            if not reuse:acquire(self.connect, key, actor['id'], pid, original['id'])
            step('Moving PSD')
            self._mapping_conflicts(pid, original)
            moved = self.source(captured) if reuse else self._move(key, actor, lease, product)
            if reuse:self._step(key, actor, lease, stage, moved=deepcopy(moved))
            step('Saving mapping')
            with self._guard(key, actor, lease) as (row, op, task, cur):
                self._edition(read_edition(self.connect, pid), task)
                if not reuse:
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
                # Fence a concurrent edition restart through final persistence.
                cur.execute('SELECT active_edition_run_id FROM edition_products WHERE id=%s FOR UPDATE',(task['edition_id'],))
                if str(cur.fetchone()['active_edition_run_id']) != str(task['run_id']):
                    raise ValueError('The edition run changed before finalisation.')
                cur.execute('SELECT status FROM edition_runs WHERE id=%s FOR UPDATE',(task['run_id'],))
                if cur.fetchone()['status'] != 'active':
                    raise ValueError('The edition run is no longer active.')
                self._edition(read_edition(self.connect,pid),task)
                cur.execute('SELECT dropbox_file_id,file_path FROM product_psd_mappings WHERE shopify_product_gid=%s FOR UPDATE',(pid,))
                final_mapping=cur.fetchone()
                if not final_mapping or final_mapping['dropbox_file_id']!=moved['id'] or final_mapping['file_path']!=moved['path_display']:
                    raise ValueError('The PSD mapping changed before finalisation. Nothing was replaced.')
                task.update(state='Mapped', error='', verified_at=now().isoformat(), preparation_held=False,
                            elapsed_ms=round((monotonic()-started)*1000,2))
                if stage not in task['completed']: task['completed'].append(stage)
                task.setdefault('timings_ms', {})[stage] = round((monotonic()-phase)*1000,2)
                # Publish readiness and admit the existing preparation queue in
                # one transaction. The database guard rejects earlier admission.
                import json
                cur.execute('UPDATE product_upload_intakes SET data=%s::jsonb WHERE id=%s',(json.dumps(row['data']),key))
                from auto_editions_onboarding_store import Queue
                import auto_editions as ae
                if not reuse:
                    expected_source=ae.source_identity(pid,moved)
                    Queue(self.connect).enqueue_cursor(cur,pid,moved['id'],str(actor['id']),expected_source=expected_source)
                    cur.execute('UPDATE auto_edition_onboarding SET source=%s::jsonb WHERE product_gid=%s AND file_id=%s AND source IS NULL',
                                (json.dumps(expected_source),pid,moved['id']))
                self.mappings._audit(cur,pid,'attach',str(actor['id']),None,dict(product_id=pid,run_id=task['run_id'],ready=True,source=moved))
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Upload Map failed: operation=%s stage=%s', key, stage)
            if isinstance(error,(ValueError,PermissionError)):
                message = str(error)
            else:
                cause = 'service unavailable' if isinstance(error,(ConnectionError,TimeoutError)) else 'unexpected application error (' + type(error).__name__ + ')'
                message = f'{stage} failed: {cause}. Retry to resume; completed steps and the original PSD identity are retained. If it persists, check server logs for mapping {key}.'
            with self.store.locked(key, actor['id']) as (row, cur):
                task = operation(row).get('sync_map', {})
                if task.get('lease') == lease:
                    task.update(state='Waiting for product in Edition Ops' if getattr(error,'waiting',False) or hasattr(error,'candidates') else 'Mapping failed',
                                needs_product=hasattr(error,'candidates'), candidates=getattr(error,'candidates',[]),
                                error=message, resume_upload_id=getattr(error,'resume_upload_id',None), stage=stage, elapsed_ms=round((monotonic()-started)*1000,2))
        finally:
            with self.store.locked(key, actor['id']) as (row, cur):
                task = operation(row).get('sync_map', {})
                if task.get('lease') == lease: task['lease_until'] = None
        return self.status(key, actor)

    def _verify_database(self, cur, key, op, task):
        from product_upload_mapping_hold import verify
        pid = op['product_id']; meta = task['moved']
        if not task.get('reused_mapping'):verify(cur, key, pid, meta['id'])
        edition = self._edition(read_edition(self.connect, pid), task)
        mapping = self.mappings.read_one(pid)
        if not mapping or (task.get('reused_mapping') and not mapping.get('verified')) or mapping['dropbox_file_id'] != meta['id'] or mapping['file_path'] != meta['path_display']:
            raise ValueError('The authoritative PSD mapping does not match the verified destination.')
        return edition

    def _status_row(self, row):
        op = row['data'].get('upload_operation') or {}; task = op.get('sync_map') or {}
        result = dict(state=task.get('state','Unmapped'), reason=task.get('error',''), stage=task.get('stage',''),
                      completed=task.get('completed',[]), needs_limit=task.get('needs_limit',False), product=op.get('product'), needs_product=task.get('needs_product',False), candidates=task.get('candidates',[]),
                      psd=(task.get('moved') or op.get('source') or {}).get('path_display',''),
                      edition_id=task.get('edition_id'), run_id=task.get('run_id'), edition_limit=task.get('confirmed_limit'),
                      resume_upload_id=task.get('resume_upload_id'), preparation_held=task.get('preparation_held',False), elapsed_ms=task.get('elapsed_ms'),
                      timings_ms=task.get('timings_ms',{}))
        if result['state']=='Mapping…' and (not task.get('lease_until') or datetime.fromisoformat(task['lease_until'])<=now()):
            result.update(state='Mapping incomplete',reason='Mapping was interrupted. Retry to resume its saved steps.')
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
                if task.get('mode') != row['mode']: raise ValueError('Upload mode changed. Retry Map.')
            result = self._status_row(row)
            if result['state']=='Mapped':
                with self.connect() as conn, conn.cursor() as cur:
                    self._verify_database(cur,key,op,task)
                result['reason'] = 'Success — PSD mapped'
            return result
        except Exception as error:
            return dict(state='Status unavailable', reason=str(error) if isinstance(error,ValueError) else
                        'Could not verify saved mapping status. Retry Map; no mapping was changed.')
