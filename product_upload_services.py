"""Adapters to the existing Files, Shopify, Edition Ops and Companion services."""
import os
import re
import unicodedata
from urllib.parse import urlsplit, unquote

from product_upload_intake import Intakes


def enabled():
    return os.getenv('PRODUCT_UPLOAD_AUTOMATIC_ENABLED', '').lower() in ('1', 'true')


class Dropbox:
    def __init__(self):
        import files_upload_api as files
        import dropbox_integration as dbx
        self.api = dbx
        self.context = files._dropbox_context()
        self.token = self.context['access_token']

    def destination(self, key):
        # Use the existing configured Product Upload Assets area for intake;
        # the authoritative design-live archive is entered only after Shopify.
        root = self.api.folder_path('product_upload_assets')
        self.api.ensure_folder_path(self.token, root, root_path=self.context['root_path'])
        return root.rstrip('/') + '/product-upload-' + key + '.psd'

    def archive(self, key, source):
        import psd_directory
        root = self.api.get_file_metadata(self.token, psd_directory.ROOT)
        if root.get('.tag') != 'folder' or not root.get('id'):
            raise ValueError('The design live online PSD destination is unavailable. Your staged PSD is retained.')
        destination = root['path_display'].rstrip('/') + '/product-upload-' + key + '.psd'
        old = self.metadata_if_present(destination)
        if old:
            if old.get('id') != source['id'] or old.get('content_hash') != source['content_hash']:
                raise ValueError('Archive destination conflict; the existing artwork is preserved.')
            return old
        current = self.metadata_if_present(source['id'])
        if not current or any(current.get(k) != source.get(k) for k in ('id','rev','content_hash')):
            raise ValueError('Staged source changed; review the original before retrying.')
        moved = self.api.move_path(self.token, source['id'], destination, root_path=self.context['root_path'])
        if moved.get('id') != source['id'] or moved.get('content_hash') != source['content_hash']:
            raise ValueError('PSD archive identity verification failed; retain the saved intake and retry.')
        return moved

    def render_destination(self, key):
        return self.destination(key).removesuffix('.psd') + '-mockup-render-v1.png'

    def download(self, metadata, destination, *, progress=None):
        # Reuse Files' authenticated, revision-pinned content download. The
        # original stays server-side; reject metadata mismatches before writing.
        from pathlib import Path
        actual, response = self.api.get_psd_file_response(self.token, metadata['id'], metadata['rev'])
        created = False
        try:
            if any(actual.get(k) != metadata.get(k) for k in ('id', 'rev', 'size', 'content_hash')):
                raise self.api.DropboxSourceChangedError('The original does not match the selected PSD revision. Refresh the Dropbox picker and reselect the PSD.')
            written = 0
            notified = 0
            signature = bytearray()
            with Path(destination).open('xb') as output:
                created = True
                for chunk in response.iter_content(chunk_size=64*1024):
                    written += len(chunk)
                    if written > metadata['size']:
                        raise self.api.DropboxOriginalDownloadError('Dropbox returned more bytes than the selected PSD. Retry artwork preparation.')
                    signature.extend(chunk[:max(0, 6-len(signature))])
                    output.write(chunk)
                    if progress and (written-notified>=1024*1024 or written==metadata['size']):
                        progress(written,metadata['size']);notified=written
            if written != metadata['size'] or signature != b'8BPS\x00\x01':
                raise self.api.DropboxOriginalDownloadError('Dropbox returned an incomplete or invalid original PSD. Retry artwork preparation.')
        except Exception:
            if created:
                Path(destination).unlink(missing_ok=True)
            raise
        finally:
            response.close()

    def save_render(self, key, path):
        target = self.render_destination(key)
        old = self.metadata_if_present(target)
        from auto_editions import file_hash
        expected = file_hash(path, dropbox=True)
        if old:
            if old.get('content_hash') != expected:
                raise ValueError('A different render already exists for this upload; retain it for review.')
            return old
        self.api.upload_local_file(self.token, target, path, conflict='cancel')
        result = self.metadata_if_present(target)
        if not result or result.get('content_hash') != expected:
            raise ValueError('Rendered artwork upload verification failed; retry the same render.')
        return result

    def start(self):
        return self.api.start_upload_session(self.token)

    def append(self, session, offset, content):
        client = getattr(self, '_append_client', None)
        if client is None:
            # A scoped clone retains the cached connection pool/path-root/auth.
            # Positive limits are intentional: this SDK's clone uses `or`, so
            # passing zero would retain its unbounded rate-limit retry default.
            client = self.api.team_space_client(self.token).clone(
                max_retries_on_error=1, max_retries_on_rate_limit=1, timeout=60)
            self._append_client = client
        return self.api.append_upload_session(self.token, session, offset, content, client=client)

    def finish(self, session, size, destination):
        return self.api.finish_upload_session(self.token, session, size, b'', destination, mode='add')

    def metadata_if_present(self, path):
        try:
            return self.api.get_file_metadata(self.token, path)
        except self.api.DropboxApiError as error:
            if 'not_found' in str(error):
                return None
            raise

    def mockups(self):
        path = self.context['root_path'].rstrip('/') + '/04_OUTPUT/product-images'
        try:
            row = self.api.get_file_metadata(self.token, path)
            if row.get('.tag') != 'folder' or not str(row.get('id', '')).startswith('id:'):
                raise ValueError()
            # Resolve the stable ID again; a guessed path is never a navigation fallback.
            resolved = self.api.get_file_metadata(self.token, row['id'])
            if resolved.get('id') != row['id'] or not self.api.path_is_within_root(resolved['path_display'], self.context['root_path']):
                raise ValueError()
            return dict(id=row['id'], path=resolved['path_display'])
        except Exception as error:
            raise ValueError('Find Mockups could not verify the product-images folder under 04_OUTPUT in the connected Team Folder. Check Files access and retry.') from error


def normal_title(value):
    return ' '.join(unicodedata.normalize('NFC', str(value)).split()).casefold()


def resolve_products(value, shopify=None):
    if shopify is None:
        import shopify_sync as shopify
    value = str(value).strip()
    if not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError('Paste the exact Shopify product name or product URL.')
    config = shopify.get_config()
    domain = config['store_domain'].lower()
    parsed = urlsplit(value)
    target_id = None; handle = None
    if re.match(r'^(?:[a-zA-Z][a-zA-Z0-9+.-]*://|//)', value):
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            raise ValueError('Use a clean HTTPS Shopify product URL.')
        path = unquote(parsed.path).rstrip('/')
        if parsed.hostname == 'admin.shopify.com':
            match = re.fullmatch(r'/store/([^/]+)/products/([1-9][0-9]*)', path)
            if not match or match[1] != domain.removesuffix('.myshopify.com'):
                raise ValueError('This product URL belongs to a different Shopify store.')
            target_id = match[2]
        elif parsed.hostname in {domain, os.getenv('SHOPIFY_PUBLIC_DOMAIN', '').lower()}:
            match = re.fullmatch(r'/admin/products/([1-9][0-9]*)', path)
            if match:
                target_id = match[1]
            else:
                match = re.fullmatch(r'/products/([^/]+)', path)
                if not match:
                    raise ValueError('Use a Shopify product or admin product URL.')
                handle = match[1]
        else:
            raise ValueError('The URL must belong to the connected Shopify store. You can also paste its exact product name.')
    if target_id:
        return [shopify.fetch_product_by_shopify_id(target_id, config=config)]
    term = handle or value
    escaped = term.replace('\\', '\\\\').replace('"', '\\"')
    query = ('handle' if handle else 'title') + ':"' + escaped + '"'
    rows = {}; cursor = None
    for _ in range(50):
        page = shopify.fetch_catalog_page(after=cursor, search=query, page_size=100, config=config)
        for p in page['products']:
            if (p.get('handle') == handle if handle else normal_title(p.get('title')) == normal_title(value)):
                rows[p['shopify_product_id']] = p
        if not page['has_next_page']:
            return list(rows.values())
        if not page.get('end_cursor') or cursor == page['end_cursor']:
            break
        cursor = page['end_cursor']
    raise ValueError('Product lookup is too broad or incomplete. Paste the exact product admin URL instead.')


def register_product(product):
    """Use canonical registration; explicit intake also supports unpublished drafts.

    Drafts use the same locked upsert. No status/price/title mutation, mirror,
    allocation or certificate operation is requested by this explicit route.
    """
    import supabase_backend as db
    import shopify_sync
    if product.get('status', '').upper() == 'ACTIVE':
        result = db.register_shopify_products_for_edition_ops([product], source='product_upload', missing_only=True)
    elif product.get('status', '').upper() == 'DRAFT':
        probe = dict(product, status='ACTIVE', online_store_url='intake-draft-validation')
        decision = shopify_sync.edition_registration_eligibility(probe)
        if not decision['eligible']:
            raise ValueError('This draft is not an eligible Sports Cave Framed Art product: ' + decision['reason'])
        result = db.upsert_shopify_products_to_edition_products([product], source='product_upload_draft',
                    sync_inserted_metafields=False, sync_variants=False, missing_only=True, include_intake_drafts=True)
    else:
        raise ValueError('Archived products cannot enter the automatic upload route.')
    if result.get('errors'):
        raise ValueError('Product sync is incomplete. Your PSD is retained; retry to finish the existing registration.')
    return result


class Handoff:
    def __init__(self, connect, provider, *, lookup=resolve_products, register=register_product, mappings=None, queue=None, shopify=None):
        from psd_mapping_store import PostgresMappings
        from auto_editions_onboarding_store import Queue
        self.store = Intakes(connect); self.provider = provider
        self.lookup = lookup; self.register = register; self.shopify = shopify
        self.mappings = mappings or PostgresMappings(connect)
        self.queue = queue or Queue(connect)

    def resolve(self, key, actor, value):
        # Save the lookup before external I/O, including not-found/network failure.
        with self.store.locked(key, actor['id']) as (row, cur):
            if row['data'].get('product_gid'):
                return row
            if not row['data'].get('copied') or not row['data'].get('source'):
                raise ValueError('Finish uploading and copy the selected prompt first.')
            row['data']['lookup'] = str(value).strip()
        choices = self.lookup(value)
        clean = [dict(id=p['shopify_product_id'], title=p['title'], handle=p.get('handle'), status=p.get('status'),
                      url=p.get('admin_url', ''), updated=p.get('updated_at', '')) for p in choices]
        with self.store.locked(key, actor['id']) as (row, cur):
            row['data']['choices'] = clean
            row['data']['reason'] = '' if choices else 'Product not found yet. Your PSD and name are saved. Wait for ChatGPT to finish, then retry.'
        if len(clean) == 1:
            return self.link(key, actor, clean[0]['id'])
        return self.store.read(key, actor['id'])

    def link(self, key, actor, pid):
        import auto_editions as ae
        import shopify_sync
        shopify = self.shopify or shopify_sync
        selected = self.store.read(key, actor['id'])
        if selected and selected['data'].get('workflow_version') == 3:
            from product_upload_lifecycle import confirm
            return confirm(self, key, actor, pid, shopify)
        with self.store.locked(key, actor['id']) as (row, cur):
            d = row['data']
            if d.get('product_gid') == pid:
                return row
            if not d.get('copied') or pid not in {p['id'] for p in d.get('choices', [])}:
                raise ValueError('Choose a product from the current exact lookup results.')
            if d.get('product_gid') and d['product_gid'] != pid:
                raise ValueError('This upload is already bound to a different product.')
            meta = self.provider.metadata_if_present(d['source']['id'])
            source = ae.source_identity(pid, meta or {})
            previous_source = ae.source_identity(pid, d['source'])
            if source != previous_source:
                # A prior archive move may have committed while its response/DB
                # transaction was lost. Recover only this deterministic target.
                import psd_directory
                expected_path=psd_directory.ROOT+'/product-upload-'+str(row['id'])+'.psd'
                if not (d.get('workflow_version')==2 and meta.get('path_display','').casefold()==expected_path.casefold() and source['file_id']==previous_source['file_id'] and source['content_hash']==previous_source['content_hash']):
                    raise ValueError('The saved PSD changed. Start a new upload; previous preparation cannot be reused.')
            product = shopify.fetch_product_by_shopify_id(pid)
            previous = next(p for p in d['choices'] if p['id'] == pid)
            if normal_title(product['title']) != normal_title(previous['title']):
                raise ValueError('Shopify title changed during lookup. Retry the exact name or URL.')
            status = product.get('status', '').upper()
            if d.get('workflow_version') == 2 and row['mode'] == 'LIVE' and (status != 'ACTIVE' or not product.get('online_store_url')):
                raise ValueError('Shopify has not confirmed live publication. Finish publishing in ChatGPT, then retry this same upload.')
            if d.get('workflow_version') == 2 and row['mode'] == 'DRAFT' and status != 'DRAFT':
                raise ValueError('This action expects a confirmed Shopify draft. Select the intended action before linking.')
            existing = self.mappings.read().get(pid)
            if existing and existing['dropbox_file_id'] != source['file_id']:
                raise ValueError('A different PSD is already mapped. Use Edition Ops Reset / Replace to explicitly replace it; the existing design is preserved.')
            if d.get('workflow_version') == 2:
                if not d.get('mockups_exported'):
                    raise ValueError('Save or download this design completed mockup package before the Shopify handoff.')
                # Moving preserves Dropbox file ID and pixels. A lost response
                # is recovered at the deterministic target without a second file.
                meta = self.provider.archive(str(row['id']), d['source'])
                d.update(source=meta, archived_source=meta, shopify_status=status,
                         shopify_completion='Published live' if status == 'ACTIVE' and product.get('online_store_url') else 'Draft confirmed')
                source = ae.source_identity(pid, meta)
            self.register(product)
            existing = self.mappings.read().get(pid)
            if existing and existing['dropbox_file_id'] != source['file_id']:
                raise ValueError('A different PSD is already mapped. Use Edition Ops Reset / Replace to explicitly replace it; the existing design is preserved.')
            if not existing:
                self.mappings.attach(pid, meta, actor, confirm_mismatch=True)
            # A prior mapping commit survives any error here; retry only completes
            # this checkpoint, using the queue's existing deduplication rules.
            self.queue.enqueue(pid, source['file_id'], str(actor['id']))
            d.update(product_gid=pid, product_title=product['title'], product_url=product.get('admin_url', ''),
                     bound_source=source, state='Waiting for Companion', reason='', choices=[])
            return row


def reconcile(row, connect):
    """Read small DB evidence only. Never download/render a PSD while polling."""
    import auto_editions as ae
    d = row['data']; pid = d.get('product_gid')
    if not pid:
        return row
    from product_upload_readiness import complete
    from auto_editions_technical import enabled as technical_enabled
    try:
        complete(connect, pid)
    except ValueError as error:
        d.update(state='Failed', reason=str(error), preview_url=None)
        return row
    with connect() as conn, conn.cursor() as cur:
        sql='''SELECT q.*,p.manifest,p.proofs,p.receipts,p.hash,m.dropbox_file_id,
            ep.edition_total AS current_total,si.metadata AS inventoried_source,
            EXISTS(SELECT 1 FROM auto_edition_preparation_hosts h WHERE h.revoked_at IS NULL
              AND h.expires_at>now() AND h.last_seen_at>now()-interval '150 seconds') AS connected
            FROM auto_edition_onboarding q LEFT JOIN auto_edition_preparations p ON p.hash=q.preparation_hash
            JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
            LEFT JOIN auto_edition_source_inventory si ON si.file_id=m.dropbox_file_id
            JOIN edition_products ep ON COALESCE(NULLIF(ep.shopify_product_gid,''),ep.shopify_product_id)=q.product_gid
            WHERE q.product_gid=%s'''
        if technical_enabled():
            sql=sql.replace('q.*,','q.*,tc.state AS technical_state,tc.reason AS technical_reason,',1)
            sql=sql.replace('WHERE q.product_gid=%s', '''LEFT JOIN LATERAL(SELECT state,reason FROM auto_edition_technical_checks
                WHERE product_gid=q.product_gid AND preparation_hash=q.preparation_hash ORDER BY updated_at DESC LIMIT 1) tc ON true
                WHERE q.product_gid=%s''')
        cur.execute(sql, (pid,))
        q = cur.fetchone()
    if not q:
        d.update(state='Failed', reason='Mapping saved; queue handoff is incomplete. Retry Upload to finish it.')
        return row
    d['companion_connected'] = bool(q['connected'])
    if (q['dropbox_file_id'] != d['bound_source']['file_id'] or q.get('source') and q['source'] != d['bound_source']
            or q.get('inventoried_source') and ae.source_identity(pid,q['inventoried_source']) != d['bound_source']):
        d.update(state='Failed', reason='PSD mapping or revision changed. Previous results were invalidated.', preparation_hash=None, preview_url=None)
        return row
    if q.get('hash') and q['status']=='Cloud Ready':
        try:
            from auto_editions_bulk import evidence
            from auto_editions_technical import colour_snapshot
            with colour_snapshot(connect):
                manifest = evidence(q)
            if manifest['source'] != d['bound_source'] or manifest['edition_total'] != q['current_total']:
                raise ValueError('Preparation no longer matches this PSD and edition limit.')
            if technical_enabled():
                from auto_editions_status import batch
                verified=batch(connect,[pid],evidence=True)['rows'][0]
                if verified['status']!='Cloud Ready':
                    raise ValueError(verified['reason'] or 'Technical completion is no longer current.')
            # Technical-only completion belongs to this intake, not approval of
            # the backlog, a production layout, or permission to fulfil orders.
            d.update(state='Cloud Ready', reason='Technical preparation and saved upload receipts verified.',
                     preparation_hash=q['hash'], preparation=dict(reference_template='SC_Auto_Editions_Base_Template_V1',
                     reference_template_sha256='257422386b980bfaac7cad1501574a01fc1ff53f03b4577ee59926d3c210b4be',
                     template_scope='layer-role contract only; no template artwork substituted',
                     source=manifest['source'], colour=manifest.get('colour_evidence'),
                     confirmed_roles=manifest.get('confirmed_roles'),policy='product-upload-technical-v1'),
                     preview_url='/api/product-uploads/preview?id=' + str(row['id']) + '&hash=' + q['hash'])
        except ValueError as error:
            d.update(state='Failed', reason=str(error), preview_url=None)
    elif q['status']=='Blocked' and q.get('hash') and technical_enabled():
        from auto_editions_status import reason
        if q.get('technical_state') in ('Failed','Superseded'):
            d.update(state='Failed',reason=reason(q.get('technical_reason')) or 'Technical verification failed. Inspect Worker Diagnostics and retry.')
        else:
            d.update(state='Uploading prepared files',reason='The existing technical worker is verifying prepared assets and durable upload receipts.')
    elif q['status'] in ('Blocked', 'Needs PSD Repair'):
        from auto_editions_status import reason
        d.update(state='Failed', reason=reason(q.get('reason')) or 'Preparation failed. Inspect Edition Ops and retry after correcting the PSD.')
    elif q['status'] == 'Preparing':
        d.update(state=('Uploading prepared files' if q.get('reason') in ('Uploading','Verifying') else 'Preparing') if q['connected'] else 'Waiting for Companion',
                 reason='' if q['connected'] else 'Companion is offline or recovering. Your uploaded PSD is retained.')
    else:
        d.update(state='Waiting for Companion', reason='Saved in the existing Companion queue. Processing starts when Companion is available.')
    return row


def catalog_revision(connect):
    """Small durable registration marker used by the existing Edition Ops cache."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n,max(created_at) AS latest FROM product_upload_intakes WHERE data->>'product_gid' IS NOT NULL")
        row = cur.fetchone()
        return (row['n'], str(row['latest']))
