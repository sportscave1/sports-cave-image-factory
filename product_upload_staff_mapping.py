"""Publish Now: verified Shopify completion -> exact PSD -> existing Auto Editions queue."""
from hashlib import sha256
import json
from pathlib import PurePosixPath
from uuid import UUID

from product_upload_identity import tag
from product_upload_intake import Intakes


def package(job, row, receipt, planned, originals):
    source = row['data']['source']
    details = dict(job=str(UUID(str(job))), source=source, folder=planned['folder_path'],
                   files=planned['files'], originals=originals, mode=row['mode'],
                   target=(row['data'].get('metadata') or {}).get('shopify_product_id'),
                   fingerprint=receipt['export_fingerprint'])
    checksum = sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    return dict(details, version=checksum, ready_tag='sc-companion-ready-' + checksum[:32])


def require_job(cur, key, row, *, stages):
    source = row['data']['source']
    cur.execute('''SELECT stage FROM product_upload_staff_jobs WHERE COALESCE(dispatch_id,id)=%s AND intake_id=%s
        AND worker_actor=%s AND source_id=%s AND source_rev=%s AND stage=ANY(%s::smallint[])
        FOR UPDATE''',
                (key, row['id'], row['actor_id'], source['id'], source['rev'], list(stages)))
    job = cur.fetchone()
    if not job:
        raise ValueError('The paired Publish Now job no longer owns this PSD revision.')
    return job


def arm(connect, key, actor, handoff):
    """Store server-built evidence before handing the prompt to the existing extension.

    Stage 4 jobs already dispatched by a previous release keep their original protocol.
    """
    with Intakes(connect).locked(key, actor) as (row, cur):
        stage = require_job(cur, handoff['job'], row, stages=(1, 2, 3, 4))['stage']
        old = row['data'].get('staff_mapping')
        if stage == 4 and not old:
            return False
        if old and (old['job'] != handoff['job'] or old['version'] != handoff['version']):
            raise ValueError('This upload’s saved package changed after handoff. Review the original upload.')
        if row['data']['source'] != handoff['source'] or row['mode'] != handoff['mode']:
            raise ValueError('The saved PSD or upload action changed before handoff.')
        if not old:
            from product_upload_refresh_mapping import target, snapshot
            pid = target(row)
            if pid:
                handoff = dict(handoff, mapping_before=snapshot(cur, pid))
            row['data']['staff_mapping'] = handoff
            task = (row['data'].get('upload_operation') or {}).get('sync_map') or {}
            if (row['data'].get('staff_upload_attempt') == handoff['job']
                    and task.get('staff_job') == handoff['job']):
                task['source_version'] = handoff['version']
    return True


def verified_package(row, job, expected=None):
    saved = row['data'].get('staff_mapping') or {}
    if (not saved.get('verified') or saved.get('job') != str(job)
            or saved.get('source') != row['data']['source'] or saved.get('mode') != row['mode']
            or (expected is not None and saved.get('version') != expected)):
        raise ValueError('The companion has no verified WebP package for this exact Publish Now job.')
    return saved


def published_product(row, saved, shopify):
    from product_upload_mapping import tags

    marker = tag(row['id'])
    page = shopify.fetch_catalog_page(search='tag:' + marker, page_size=3)
    products = [p for p in page['products'] if marker in tags(p)]
    if page.get('has_next_page') or len(products) > 1:
        raise ValueError('Multiple Shopify listings match this upload operation. The PSD stayed in place.')
    if not products:
        return None
    product = products[0]
    if saved['ready_tag'] not in tags(product):
        return None
    pid = product['shopify_product_id']
    if saved['target'] and shopify.shopify_gid('Product', saved['target']) != pid:
        raise ValueError('Shopify returned a product other than the saved refresh target.')
    if product['status'] != 'ACTIVE' or not product.get('online_store_url'):
        return None
    if len({image.get('id') or image['url'] for image in product['images'] if image.get('url')}) < len(saved['files']):
        return None
    return product


def verify_webps(provider, saved):
    """Match the exact reserved gallery and keep the five core files pinned."""
    ids = set()
    for item in saved['files']:
        name = item['filename']
        if PurePosixPath(name).name != name or not name.lower().endswith('.webp') or '\\' in name:
            raise ValueError('The companion received an invalid WebP filename.')
        path = saved['folder'] + '/' + name
        current = provider.metadata_if_present(path)
        if not current:
            return False
        file_id = current.get('id')
        if (not file_id or file_id in ids or not current.get('rev') or not current.get('content_hash')
                or not current.get('size')
                or current.get('path_display') != path):
            raise ValueError('A saved Dropbox WebP does not match the exact upload package.')
        ids.add(file_id)
        pinned = saved['originals'].get(item['role'])
        if pinned and any(current.get(k) != pinned[field] for k, field in
                          (('id','file_id'), ('rev','revision'), ('content_hash','content_hash'), ('size','size_bytes'))):
            raise ValueError('An original Dropbox WebP changed after approval. The PSD stayed in place.')
    return True


def run(connect, job, row, progress):
    """Called by the paired Upload Companion tick. The mapping service owns all mutations."""
    import os_accounts
    import shopify_sync
    from product_upload_mapping import Mapping, read_edition
    from product_upload_services import Dropbox

    key, job_id = str(row['id']), str(job['id'])
    saved = row['data']['staff_mapping']
    if saved['job'] != job_id:
        raise ValueError('The saved companion handoff belongs to a different upload.')
    product = published_product(row, saved, shopify_sync)
    if not product:
        return False
    url, pid = product['online_store_url'], product['shopify_product_id']
    if not read_edition(connect, pid):
        progress('Shopify published · waiting for Edition Ops sync', url)
        return False
    actor_id = job['worker_actor']
    if actor_id == 'legacy-master-admin':
        actor = dict(id=actor_id, role=os_accounts.ROLE_ADMIN, is_active=True, page_permissions=[])
    else:
        actor = os_accounts.DEFAULT_STORE.get_user(actor_id)
    if not actor or not os_accounts.can_attach_missing_psd(actor):
        raise PermissionError('The paired administrator no longer has PSD attachment access.')
    provider = Dropbox()
    if not saved.get('verified'):
        if not verify_webps(provider, saved):
            progress('Shopify published · waiting for the complete Dropbox WebP package', url)
            return False
        with Intakes(connect).locked(key, actor_id) as (current, cur):
            require_job(cur, job_id, current, stages=(5,))
            package = current['data'].get('staff_mapping') or {}
            if (package.get('version') != saved['version'] or current['data']['source'] != saved['source']
                    or current['mode'] != saved['mode']):
                raise ValueError('The saved upload changed during companion verification.')
            package['verified'] = True
    if not job['storefront'] or job['message'].startswith('Shopify published · waiting for'):
        progress('Shopify published · companion is mapping the original PSD', url)
    status = Mapping(connect, provider).map(key, actor, product_id=pid, confirm_product=True,
                                            source_version=saved['version'], staff_job=job_id)
    if status['state'] == 'Mapped':
        with connect() as conn, conn.cursor() as cur:
            cur.execute('SELECT 1 FROM auto_edition_onboarding WHERE product_gid=%s AND file_id=%s',
                        (pid, saved['source']['id']))
            if not cur.fetchone():
                raise ValueError('PSD mapped, but no matching Auto Editions handoff was confirmed.')
        return url
    if status['state'] == 'Mapping failed':
        # Preserve the coordinated mapping checkpoint for another tick.
        progress(status['reason'] or 'Companion mapping needs attention. Retrying the saved PSD.', url)
    return False
