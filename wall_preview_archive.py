"""Retry confirmed composites in the existing worker; never store raw wall photos."""
import io
import logging
import posixpath
import wall_preview_crm_store as store
import wall_preview_api as archive

LOG=logging.getLogger(__name__)


class ArchiveDestinationError(ValueError):
    """A destination conflict must not be replayed as a transient storage outage."""


def configuration_diagnostic():
    missing = archive.dropbox_integration.missing_server_config_keys()
    if missing:
        LOG.warning('wall_preview_archive_config_missing keys=%s refresh_token_or_access_token_required=true', ','.join(missing))
    return missing


def _upload(row, data, token, root):
    """Overwrite one stable file; atomically move it after identity enrichment."""
    from wall_preview_identity import customer_folder_name
    db = archive.dropbox_integration
    base = root.rstrip('/')+'/'+archive.DROPBOX_RELATIVE_ROOT
    source = row['dropbox_path']
    if root.rstrip('/') != '/Sportscave Team Folder' or not db.path_is_within_root(source,base):
        raise ArchiveDestinationError('Invalid archive destination.')
    folder = row['customer_folder']
    if (row.get('attribution') or {}).get('capture_mode') == 'save_event':
        from wall_preview_identity import capture_folder
        folder = capture_folder(row,root,archive.DROPBOX_RELATIVE_ROOT)
    elif row.get('customer_email'):
        folder = base+'/'+customer_folder_name(row['customer_email'])
    if not db.path_is_within_root(folder,base):
        raise ArchiveDestinationError('Invalid archive folder.')
    # Retain the existing stable filename, including archives made before CRM v2.
    destination = folder+'/'+posixpath.basename(source)
    db.ensure_folder_path(token,folder,root_path=root)
    target = destination
    move = False
    if source != destination:
        old = db.get_metadata_if_exists(token,source)
        new = db.get_metadata_if_exists(token,destination)
        if old and new:
            raise ArchiveDestinationError('Archive relocation destination collision.')
        if old:
            target,move = source,True
        elif new and row.get('dropbox_file_id') and new.get('id') != row['dropbox_file_id']:
            raise ArchiveDestinationError('Archive relocation identity mismatch.')
        # If a previous move succeeded before DB commit, retry destination in place.
    metadata = db.upload_stream(token,target,io.BytesIO(data),size=len(data),conflict='replace')
    if move:
        metadata = db.move_path(token,source,destination,root_path=root)
    file_id = str((metadata or {}).get('id') or (metadata or {}).get('file_id') or '')
    if not file_id:
        raise ValueError('Archive provider did not confirm a file ID.')
    return file_id,destination,folder


def tick(preview_id=None):
    # Lock preview first, like confirmation. A stale version cannot replace a
    # deliberately reconfirmed image. Process one job, no detached threads.
    with store.transaction() as cur:
        cur.execute('''SELECT p.* FROM public.wall_previews p
            JOIN public.wall_preview_archive_jobs j ON j.preview_id=p.id
            WHERE j.state='queued' AND j.due_at<=now()
            AND (%s::uuid IS NULL OR p.id=%s::uuid)
            ORDER BY j.due_at FOR UPDATE OF p SKIP LOCKED LIMIT 1''',(preview_id,preview_id))
        row=dict(cur.fetchone() or {})
        if not row:return False
        from wall_preview_deletion import blocked
        if blocked(row):
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='failed',image=NULL,reason='admin_deleted',finished_at=now() WHERE preview_id=%s", (str(row['id']),))
            return True
        cur.execute("SELECT version,encode(image,'hex') AS image,attempts FROM public.wall_preview_archive_jobs WHERE preview_id=%s FOR UPDATE",(str(row['id']),))
        job=dict(cur.fetchone())
        if job['version']!=row['version'] or not job['image']:
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='failed',image=NULL,reason='obsolete_version',finished_at=now() WHERE preview_id=%s",(str(row['id']),))
            return True
        try:
            token,root=archive._dropbox_connection()
            data=bytes.fromhex(job['image'])
            file_id,path,folder=_upload(row,data,token,root)
            cur.execute('UPDATE public.wall_previews SET dropbox_file_id=%s,dropbox_path=%s,customer_folder=%s,updated_at=now() WHERE id=%s',(file_id,path,folder,str(row['id'])))
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='done',image=NULL,attempts=attempts+1,last_attempt_at=now(),finished_at=now(),reason='' WHERE preview_id=%s",(str(row['id']),))
            LOG.info('wall_preview_archive_done preview_id=%s version=%s attempt=%s',row['id'],row['version'],job['attempts']+1)
        except Exception as exc:
            permanent=isinstance(exc,ArchiveDestinationError)
            cur.execute("""UPDATE public.wall_preview_archive_jobs SET attempts=attempts+1,last_attempt_at=now(),
                state=CASE WHEN %s OR attempts+1>=5 THEN 'failed' ELSE 'queued' END,
                due_at=now()+interval '5 minutes',reason=%s,
                finished_at=CASE WHEN %s OR attempts+1>=5 THEN now() ELSE NULL END WHERE preview_id=%s""",
                (permanent,'archive_destination_conflict' if permanent else 'archive_unavailable',permanent,str(row['id'])))
            if isinstance(exc,archive.dropbox_integration.DropboxConfigError):configuration_diagnostic()
            LOG.warning('wall_preview_archive_%s preview_id=%s version=%s attempt=%s error_type=%s',
                'failed' if permanent or job['attempts']+1>=5 else 'retry',row['id'],row['version'],job['attempts']+1,type(exc).__name__)
    return True
