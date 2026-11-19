"""Exact, administrator-approved refresh handoff; retains edition history and old files."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import PurePosixPath


def refresh_path(destination, source):
    name = PurePosixPath(destination)
    suffix = sha256(source['id'].encode()).hexdigest()[:12]
    return str(name.with_name(name.stem[:200] + '__refresh_' + suffix + name.suffix))


def snapshot(cur, pid):
    cur.execute('SELECT dropbox_file_id,file_path,updated_at FROM product_psd_mappings WHERE shopify_product_gid=%s', (pid,))
    row = cur.fetchone()
    return {k: str(v) for k, v in row.items()} if row else None


def target(row):
    if not row:
        return None
    meta = row['data'].get('metadata') or {}
    if row['mode'] == 'UPDATE' and meta.get('upload_intent') == 'existing_product_refresh':
        from psd_directory import product_id
        return product_id({'shopify_product_gid': meta.get('shopify_product_id')})
    return None


def run(service, key, actor, version, job):
    """One locked mapping/queue commit. A lost Dropbox move reply resumes by ID/hash."""
    import os_accounts
    import auto_editions as ae
    from auto_editions_onboarding_store import Queue
    from product_upload_mapping import now, operation, read_edition, summary
    from product_upload_staff_mapping import require_job
    from product_upload_dropbox import verify_roots, within
    from product_upload_mapping_hold import held

    prior = service.store.read(key, actor['id'])
    pid = target(prior)
    if not pid or not job:
        return None
    if not os_accounts.is_admin(actor):
        raise PermissionError('Only an administrator can replace a refreshed product PSD.')
    saved = service._saved_package(prior, version, job)
    if 'mapping_before' not in saved:
        raise ValueError('This older refresh needs its existing PSD mapping reviewed before handoff. No mapping was replaced.')
    if not saved['mapping_before']:
        return None  # A refresh with no prior mapping uses normal first attachment.
    if (prior['data'].get('upload_operation') or {}).get('sync_map', {}).get('state') == 'Mapped':
        return service.status(key, actor)
    product = service._identity(key, prior, pid, True)
    if product['shopify_product_id'] != pid or saved['target'] != pid:
        raise ValueError('The refreshed publication no longer matches its approved product.')
    roots = verify_roots(service.provider)
    with service.store.locked(key, actor['id'], provider_io=True) as (row, cur):
        saved = service._saved_package(row, version, job)
        require_job(cur, job, row, stages=(5,))
        if target(row) != pid or saved['mapping_before'] != prior['data']['staff_mapping']['mapping_before']:
            raise ValueError('The approved refresh changed before mapping.')
        op = operation(row)
        task = op.setdefault('sync_map', {})
        if task.get('manual_takeover'):
            raise ValueError('This refresh was retired by manual mapping.')
        # Same lock order as mapping and preparation admission. No worker may
        # claim a generation while its source association is being replaced.
        cur.execute('LOCK TABLE edition_products IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('LOCK TABLE product_psd_mappings IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('LOCK TABLE auto_edition_onboarding,auto_edition_jobs IN SHARE ROW EXCLUSIVE MODE')
        if task.get('state') == 'Mapped':
            return service._status_row(row)
        if snapshot(cur, pid) != saved['mapping_before']:
            raise ValueError('The existing PSD mapping changed after refresh approval. Nothing was replaced.')
        source = op['source']
        cur.execute('SELECT shopify_product_gid FROM product_psd_mappings WHERE dropbox_file_id=%s AND shopify_product_gid<>%s', (source['id'], pid))
        if cur.fetchone():
            raise ValueError('This PSD already maps to a different Shopify product.')
        if held(cur, pid, source['id']):
            raise ValueError('Another upload owns this product’s unfinished mapping.')
        cur.execute("""SELECT 1 FROM auto_edition_onboarding q WHERE product_gid=%s AND
            (status='Preparing' OR lease_until>now() OR to_jsonb(q)->'replacement'->>'stage' IN ('Discovering','Queued','Preparing')
             OR to_jsonb(q)->'replacement'->>'manual_required'='true'
             OR to_jsonb(q)->'reset_cancellation'->>'stage' IN ('Cancelling','Confirmed'))""", (pid,))
        if cur.fetchone():
            return dict(state='Mapping failed', reason='Shopify published · waiting for existing Auto Editions work to finish before PSD refresh')
        cur.execute("SELECT 1 FROM auto_edition_jobs WHERE payload->'identity'->'source'->>'product_gid'=%s AND status IN ('Queued','Generating')", (pid,))
        if cur.fetchone():
            return dict(state='Mapping failed', reason='Shopify published · waiting for existing edition rendering before PSD refresh')
        edition = service._edition(read_edition(service.connect, pid), task)
        cur.execute('SELECT status FROM edition_runs WHERE id=%s FOR UPDATE', (edition['run_id'],))
        if cur.fetchone()['status'] != 'active':
            raise ValueError('The edition run changed before refresh mapping. Its history was preserved.')
        destination = roots['live']['path'] + '/' + source['path_display'].rsplit('/', 1)[-1]
        current = service.source(row)
        occupied = service.provider.metadata_if_present(destination)
        if occupied and occupied['id'] != source['id']:
            # Keep the previous master in place. The stable source-ID suffix
            # also lets a lost move response reconcile to exactly the same path.
            destination = refresh_path(destination, source)
            occupied = service.provider.metadata_if_present(destination)
            if occupied and occupied['id'] != source['id']:
                raise ValueError('Destination conflict: the reserved refresh path contains another PSD. Nothing was overwritten.')
        if current['path_display'] != destination and not within(current['path_display'], roots['review']['path']):
            raise ValueError('The refreshed PSD is outside the approved Review folder.')
        if current['path_display'] != destination:
            service.provider.api.move_path(service.provider.token, source['id'], destination,
                                           root_path=service.provider.context['root_path'])
        moved = service.provider.metadata_if_present(source['id'])
        if not moved or moved.get('path_display') != destination or not moved.get('rev') or any(moved.get(k) != source.get(k) for k in ('id','content_hash','size')):
            raise ValueError('Dropbox did not verify the exact refreshed PSD destination. Retry the saved upload.')
        # Source movement is the only external mutation. Both DB association and
        # preparation admission commit together; old preparations/files survive.
        cur.execute("UPDATE product_psd_mappings SET dropbox_file_id=%s,file_path=%s,source='manual',actor_id=%s,updated_at=now() WHERE shopify_product_gid=%s RETURNING *",
                    (moved['id'], destination, str(actor['id']), pid))
        after = dict(cur.fetchone())
        service.mappings._audit(cur, pid, 'replace', str(actor['id']), saved['mapping_before'], dict(after, source=moved, upload_operation=key))
        expected = ae.source_identity(pid, moved)
        cur.execute("""INSERT INTO auto_edition_onboarding(product_gid,file_id,source,priority)
            VALUES(%s,%s,%s::jsonb,2) ON CONFLICT(product_gid) DO UPDATE SET
            file_id=excluded.file_id,source=excluded.source,preparation_hash=NULL,status='Awaiting preparation',
            reason='',attempts=0,priority=2,lease_token=NULL,lease_until=NULL,replacement=NULL,updated_at=now()""",
                    (pid, moved['id'], json.dumps(expected)))
        cur.execute('SELECT file_id,source FROM auto_edition_onboarding WHERE product_gid=%s', (pid,))
        queued = cur.fetchone()
        if not queued or queued['file_id'] != moved['id'] or queued['source'] != expected:
            raise ValueError('The refreshed Auto Editions handoff could not be verified.')
        Queue.audit(cur, pid, str(actor['id']), 'refresh_upload_queued', dict(operation=key, source=expected))
        task.update(state='Mapped', error='', stage='Verifying', moved=deepcopy(moved),
                    reused_mapping=True, refresh_mapping=True, staff_job=job, source_version=version, mode=row['mode'],
                    edition_id=edition['id'], run_id=edition['run_id'], confirmed_limit=edition['edition_total'],
                    verified_at=now().isoformat(), preparation_held=False, lease_until=None)
        op.update(product_id=pid, shop_domain=service.shop_domain, binding=product['_upload_binding'], product=summary(product))
        row['data'].update(product_gid=pid, product_title=product['title'], shopify_completion='Listing updated')
    service.mappings._revision = None
    return service.status(key, actor)
