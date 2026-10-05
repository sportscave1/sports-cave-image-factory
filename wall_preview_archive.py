"""Retry confirmed composites in the existing worker; never store raw wall photos."""
import io
import logging
import wall_preview_crm_store as store
import wall_preview_api as archive

LOG=logging.getLogger(__name__)


def tick():
    # Lock preview first, like confirmation. A stale version cannot replace a
    # deliberately reconfirmed image. Process one job, no detached threads.
    with store.transaction() as cur:
        cur.execute('''SELECT p.* FROM public.wall_previews p
            JOIN public.wall_preview_archive_jobs j ON j.preview_id=p.id
            WHERE j.state='queued' AND j.due_at<=now()
            ORDER BY j.due_at FOR UPDATE OF p SKIP LOCKED LIMIT 1''')
        row=dict(cur.fetchone() or {})
        if not row:return False
        cur.execute("SELECT version,encode(image,'hex') AS image,attempts FROM public.wall_preview_archive_jobs WHERE preview_id=%s FOR UPDATE",(str(row['id']),))
        job=dict(cur.fetchone())
        if job['version']!=row['version'] or not job['image']:
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='failed',image=NULL,reason='obsolete_version',finished_at=now() WHERE preview_id=%s",(str(row['id']),))
            return True
        try:
            token,root=archive._dropbox_connection()
            if root.rstrip('/')!='/Sportscave Team Folder' or not archive.dropbox_integration.path_is_within_root(row['dropbox_path'],root+'/'+archive.DROPBOX_RELATIVE_ROOT):
                raise ValueError('Invalid archive destination.')
            data=bytes.fromhex(job['image'])
            archive.dropbox_integration.ensure_folder_path(token,row['customer_folder'],root_path=root)
            metadata=archive.dropbox_integration.upload_stream(token,row['dropbox_path'],io.BytesIO(data),size=len(data),conflict='replace')
            file_id=str((metadata or {}).get('id') or (metadata or {}).get('file_id') or '')
            cur.execute('UPDATE public.wall_previews SET dropbox_file_id=%s,updated_at=now() WHERE id=%s',(file_id,str(row['id'])))
            cur.execute("UPDATE public.wall_preview_archive_jobs SET state='done',image=NULL,attempts=attempts+1,last_attempt_at=now(),finished_at=now(),reason='' WHERE preview_id=%s",(str(row['id']),))
            LOG.info('wall_preview_archive_done preview_id=%s version=%s',row['id'],row['version'])
        except Exception as exc:
            cur.execute("""UPDATE public.wall_preview_archive_jobs SET attempts=attempts+1,last_attempt_at=now(),
                state=CASE WHEN attempts+1>=5 THEN 'failed' ELSE 'queued' END,
                due_at=now()+interval '5 minutes',reason='archive_unavailable',
                finished_at=CASE WHEN attempts+1>=5 THEN now() ELSE NULL END WHERE preview_id=%s""",(str(row['id']),))
            LOG.warning('wall_preview_archive_retry preview_id=%s error_type=%s',row['id'],type(exc).__name__)
    return True
