"""Admin-only, recoverable deletion of capture-owned files and inbox data.

The existing private attribution JSON stores a deletion manifest before any
provider mutation. A minimal ledger tombstone reserves retry identities forever.
No customer folder, source photograph or Shopify artwork is ever deleted.
"""
import hashlib
import json
import logging
import posixpath
import threading
import time
import uuid

import dropbox_integration as db
import os_accounts
import wall_preview_crm_store as crm
from wall_preview_store import WallPreviewStoreError

ROOT = '/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox'
MAX_BATCH = 24
_SLOT = threading.BoundedSemaphore(1)
LOG = logging.getLogger(__name__)


def blocked(row):
    state = (row or {}).get('attribution') or {}
    return bool(state.get('inbox_deletion') or state.get('inbox_deleted_at'))


def retired_email(value):
    return 'deleted-' + hashlib.sha256(str(value or '').lower().encode()).hexdigest() + '@deleted.invalid'


def validate_ids(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= MAX_BATCH:
        raise ValueError(f'Select between 1 and {MAX_BATCH} previews.')
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError('Invalid preview ID.')
        identity = str(uuid.UUID(value))
        if identity not in result:
            result.append(identity)
    return tuple(result)


def _paths(row):
    """The worker can leave either its original or intended composite after a crash."""
    source = str(row.get('dropbox_path') or '')
    if not source:
        return []
    from wall_preview_identity import capture_folder, customer_folder_name
    paths = [source]
    folder = row.get('customer_folder') or posixpath.dirname(source)
    if (row.get('attribution') or {}).get('capture_mode') == 'save_event':
        folder = capture_folder(row, '/Sportscave Team Folder', '03_ASSETS/11 Wall Preview Inbox')
    elif row.get('customer_email'):
        folder = ROOT + '/' + customer_folder_name(row['customer_email'])
    paths.append(folder.rstrip('/') + '/' + posixpath.basename(source))
    for path in paths:
        if not db.path_is_within_root(path, ROOT) or path.casefold() == ROOT.casefold() or '..' in path.split('/'):
            raise WallPreviewStoreError('Preview storage location could not be verified.')
    return list(dict.fromkeys(paths))


def _missing(error):
    value = getattr(error, 'error', None)
    for name in ('path', 'path_lookup'):
        test = getattr(value, 'is_' + name, None)
        if test and test():
            return bool(getattr(value, 'get_' + name)().is_not_found())
    return False


class Assets:
    def __init__(self):
        self._client = None
        self.retry_after = 0

    @property
    def client(self):
        if time.monotonic() < self.retry_after:
            raise WallPreviewStoreError('Dropbox rate limit reached. Wait before retrying this batch.')
        if self._client is None:
            auth = db.resolve_server_auth(validate=False)
            # Reuse the authenticated team namespace; bound SDK retries on this clone.
            self._client = db.team_space_client(auth['access_token']).clone(
                timeout=20, max_retries_on_error=1, max_retries_on_rate_limit=0)
        return self._client

    def metadata(self, reference):
        try:
            return db._metadata_to_dict(self.client.files_get_metadata(reference))
        except Exception as error:
            if _missing(error):
                return None
            self.retry_after = max(self.retry_after, time.monotonic() + max(0, float(getattr(error, 'backoff', 0) or 0)))
            raise WallPreviewStoreError('Dropbox lookup failed. Check the connection or rate limit and retry.') from error

    def resolve(self, row, paths):
        identities = {}
        file_id = row.get('dropbox_file_id') or ''
        references = ([file_id] if file_id.startswith('id:') else []) + paths
        for reference in references:
            metadata = self.metadata(reference)
            if not metadata:
                continue
            path = metadata.get('path_display') or metadata.get('path_lower') or ''
            identity = metadata.get('id') or ''
            if metadata.get('.tag') != 'file' or not identity.startswith('id:') or not db.path_is_within_root(path, ROOT):
                raise WallPreviewStoreError('Only verified preview files can be deleted; folders are never removed.')
            if file_id:
                if identity != file_id:
                    raise WallPreviewStoreError('Preview storage identity changed. Review the file before retrying.')
            elif posixpath.splitext(posixpath.basename(path))[0] not in {
                str(row['id']), str(row.get('client_preview_id')), str(row.get('image_sha256'))
            }:
                raise WallPreviewStoreError('Preview file ownership could not be verified.')
            identities[identity] = {'id': identity, 'path': path, 'rev': metadata.get('rev')}
        return list(identities.values())

    def remove(self, asset):
        current = self.metadata(asset['id'])
        if current is None:
            return
        if (current.get('.tag') != 'file' or current.get('id') != asset['id']
                or not db.path_is_within_root(current.get('path_display') or current.get('path_lower') or '', ROOT)
                or (asset.get('rev') and current.get('rev') != asset['rev'])):
            raise WallPreviewStoreError('Preview file changed during deletion. Review it before retrying.')
        try:
            # File IDs survive moves and cannot accidentally delete a replacement path/folder.
            self.client.files_delete_v2(asset['id'])
        except Exception as error:
            if not _missing(error):
                self.retry_after = max(self.retry_after, time.monotonic() + max(0, float(getattr(error, 'backoff', 0) or 0)))
                raise WallPreviewStoreError('Dropbox deletion failed. The preview remains pending; retry later.') from error


def _row(cur, preview_id):
    cur.execute('SELECT * FROM public.wall_previews WHERE id=%s FOR UPDATE', (preview_id,))
    return dict(cur.fetchone() or {})


def _save_manifest(cur, preview_id, manifest):
    cur.execute("""UPDATE public.wall_previews SET attribution=attribution ||
        jsonb_build_object('inbox_deletion',%s::jsonb),share_revoked_at=now(),updated_at=now()
        WHERE id=%s""", (json.dumps(manifest), preview_id))


def _shared(cur, preview_id, asset):
    cur.execute("""SELECT id FROM public.wall_previews WHERE id<>%s
        AND NOT (attribution ? 'inbox_deleted_at')
        AND ((dropbox_file_id<>'' AND dropbox_file_id=%s) OR lower(dropbox_path)=lower(%s)) LIMIT 1""",
        (preview_id, asset['id'], asset['path']))
    return bool(cur.fetchone())


def delete_one(preview_id, *, user, assets=None, remove_asset=None):
    if not os_accounts.is_admin(user):
        raise PermissionError('Only an administrator can delete previews.')
    preview_id = validate_ids([preview_id])[0]
    assets = assets or Assets()
    with crm.transaction() as cur:
        row = _row(cur, preview_id)
        if not row or (row.get('attribution') or {}).get('inbox_deleted_at'):
            return {'id': preview_id, 'status': 'already_deleted'}
        cur.execute("SELECT state FROM public.wall_preview_email_jobs WHERE preview_id=%s FOR UPDATE", (preview_id,))
        if any(job['state']=='processing' for job in cur.fetchall()):
            raise WallPreviewStoreError('An image delivery is in progress. Retry deletion shortly.')
        manifest = (row.get('attribution') or {}).get('inbox_deletion')
        if not manifest:
            manifest = {'paths': _paths(row), 'actor': str(user['id'])}
            _save_manifest(cur, preview_id, manifest)
        cur.execute("UPDATE public.wall_preview_archive_jobs SET state='failed',reason='admin_deletion_pending' WHERE preview_id=%s", (preview_id,))
        cur.execute("UPDATE public.wall_preview_email_jobs SET state='suppressed',reason='preview_deleted',finished_at=now() WHERE preview_id=%s AND state='queued'", (preview_id,))
        cur.execute("UPDATE public.wall_preview_customer_jobs SET state='failed',reason='preview_deleted',finished_at=now() WHERE preview_id=%s", (preview_id,))
    # Resolve and commit exact file identities before deleting anything. Worker
    # and storefront writes are now fenced by the persisted deletion marker.
    with crm.transaction() as cur:
        row = _row(cur, preview_id)
        if (row.get('attribution') or {}).get('inbox_deleted_at'):
            return {'id': preview_id, 'status': 'already_deleted'}
        manifest = row['attribution']['inbox_deletion']
        if 'assets' not in manifest:
            manifest['assets'] = [] if remove_asset else assets.resolve(row, manifest['paths'])
            _save_manifest(cur, preview_id, manifest)
    with crm.transaction() as cur:
        # Serialize shared-file ownership checks across every server process.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('wall-preview-delete',0))")
        row = _row(cur, preview_id)
        if row['attribution'].get('inbox_deleted_at'):
            return {'id': preview_id, 'status': 'already_deleted'}
        manifest = row['attribution']['inbox_deletion']
        preserved = 0
        if remove_asset and row.get('dropbox_path'):
            asset = {'id': row.get('dropbox_file_id') or '', 'path': row['dropbox_path']}
            if _shared(cur, preview_id, asset):
                preserved += 1
            else:
                remove_asset(row)
        for asset in manifest['assets']:
            if _shared(cur, preview_id, asset):
                preserved += 1
            else:
                assets.remove(asset)
        _finish(cur, row, user)
    try:
        import activity_log
        activity_log.record_activity_log('wall_preview_deleted','Social Media','Wall preview deleted',
            entity_type='wall_preview',entity_id=preview_id,actor=str(user['id']),event_key='wall-preview-deleted:'+preview_id)
    except Exception:
        LOG.warning('wall_preview_delete_audit_unavailable preview_id=%s', preview_id)
    return {'id': preview_id, 'status': 'deleted', 'shared_files_preserved': preserved}


def _finish(cur, row, user):
    preview_id = str(row['id'])
    cur.execute('DELETE FROM public.wall_preview_events WHERE preview_id=%s OR client_preview_id=%s', (preview_id, row.get('client_preview_id')))
    for table in ('wall_preview_archive_jobs','wall_preview_email_jobs','wall_preview_customer_jobs'):
        cur.execute(f'DELETE FROM public.{table} WHERE preview_id=%s', (preview_id,))
    # Reserve the old deduplication keys without retaining contact information,
    # image bytes, file locations, attribution, orders, shares or product metadata.
    cur.execute("""UPDATE public.wall_previews SET attribution=jsonb_build_object(
        'inbox_deleted_at',now(),'inbox_deleted_by',%s::text),status='archived',
        customer_email=%s,customer_name='',shopify_customer_id='',customer_folder='',session_id=NULL,
        identity_source='',email_marketing_state='UNKNOWN',measurement_unit='',
        image_width=1,image_height=1,image_bytes=1,save_count=1,
        confirmed_at=NULL,started_at=NULL,email_requested_at=NULL,email_sent_at=NULL,purchased_at=NULL,
        reviewed_at=NULL,reviewed_by=NULL,share_expires_at=NULL,
        product_id='',variant_id='',product_handle='',product_title='',product_url='',frame_label='',size_label='',
        dropbox_file_id='',dropbox_path='',archive_sha256=NULL,notes='',marketing_permission=false,
        share_token=NULL,share_revoked_at=now(),order_id=NULL,order_number=NULL,
        submitted_marketing_opt_in=NULL,marketing_consent_text=NULL,marketing_consent_version=NULL,
        marketing_consent_source=NULL,marketing_consent_at=NULL,image_reuse_consent_at=NULL,
        image_reuse_consent_source=NULL,market_country_code=NULL,market_country_name=NULL,updated_at=now()
        WHERE id=%s""", (str(user['id']), retired_email(row.get('customer_email')) if not row.get('client_preview_id') else '', preview_id))


def bulk_delete(preview_ids, *, user, progress=None, assets=None):
    if not os_accounts.is_admin(user):
        raise PermissionError('Only an administrator can delete previews.')
    ids = validate_ids(preview_ids)
    if not _SLOT.acquire(blocking=False):
        raise WallPreviewStoreError('Another deletion is running. Please retry shortly.')
    results = []
    try:
        assets = assets or Assets()
        for identity in ids:
            try:
                result = delete_one(identity, user=user, assets=assets)
            except Exception as error:
                LOG.warning('wall_preview_delete_failed preview_id=%s error_type=%s', identity, type(error).__name__)
                result = {'id': identity, 'status': 'failed', 'error': str(error) if isinstance(error, WallPreviewStoreError)
                          else 'Deletion could not finish. Its recovery state is retained; retry this preview.'}
            results.append(result)
            if progress:
                progress(len(results), len(ids))
        return results
    finally:
        _SLOT.release()
