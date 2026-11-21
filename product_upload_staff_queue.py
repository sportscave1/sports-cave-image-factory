"""Durable staff requests, restricted to the paired desktop and exact artwork."""
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

LABELS = ('Waiting for desktop companion', 'Preparing the original PSD', 'Generating mockups',
          'Saving WebPs to Dropbox', 'Opening the ChatGPT project',
          'ChatGPT submitted · waiting for live publication and PSD mapping',
          'Published and PSD mapped', 'Needs attention')
PERCENT = (0, 12, 34, 62, 83, 93, 100, 0)
LOG = logging.getLogger(__name__)
CONTROL_KEY = 'product_upload_queue_enabled'
STALL_MINUTES = 30
CANCELLED = 'Cancelled by user.'
MAPPING_RESUME = 'Verified publication · waiting to resume PSD mapping'


def connect():
    from product_upload_api import connect as upload_connect
    return upload_connect()


def enqueue(user, source, title, sport, *, ad_country=None, start=False):
    if ad_country is not None:
        import design_publish_ad as ad
        sport, ad_country = ad.check_request(user, sport, ad_country)
    from design_review_page import final_psd
    if not final_psd(source) or not source.get('id') or not source.get('rev'):
        raise ValueError('Choose a current PSD from Design Studio Review.')
    resume = start and can_control_queues(user)
    replaced = False
    with connect() as conn, conn.cursor() as cur:
        # Serialize explicit replacement with desktop claims and queue controls.
        cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',
                    ('staff-upload:' + source['id'] + ':' + source['rev'],))
        cur.execute('''INSERT INTO product_upload_staff_jobs(id,source_id,source_rev,title,sport)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT(source_id,source_rev) DO NOTHING RETURNING *''',
                    (uuid4(), source['id'], source['rev'], title, sport))
        job = cur.fetchone()
        if not job:
            cur.execute('SELECT * FROM product_upload_staff_jobs WHERE source_id=%s AND source_rev=%s',
                        (source['id'], source['rev']))
            job = cur.fetchone()
            intake = None
            # Intake -> job is also the mapping worker's lock order.
            if job['stage'] != 0 and job['intake_id']:
                cur.execute('SELECT data FROM product_upload_intakes WHERE id=%s FOR UPDATE', (job['intake_id'],))
                intake = cur.fetchone()
            cur.execute('SELECT * FROM product_upload_staff_jobs WHERE id=%s FOR UPDATE', (job['id'],))
            job = cur.fetchone()
            if job['stage'] != 0:
                job = _reset_attempt(cur, job, intake)
                replaced = True
        key = job['id']
        if resume and job['stage'] < 6:
            cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,'true'::jsonb,now())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()''', (CONTROL_KEY,))
        cur.execute('''INSERT INTO product_upload_staff_requests(requester,job_id)
            VALUES (%s,%s) ON CONFLICT DO NOTHING''', (user['id'], key))
        if ad_country is not None:
            ad.enqueue(cur, key, user['id'], sport, ad_country)
    if replaced and job['intake_id']:
        from product_upload_jobs import JOBS
        JOBS.begin_staff_attempt(str(job['intake_id']), job['worker_actor'],
                                 str(job['dispatch_id']), full=True)
    LOG.info('staff_upload_queued job=%s dispatch=%s replaced=%s',
             job['id'], job.get('dispatch_id') or job['id'], replaced)
    # A committed request must not leave the header showing a cached completion.
    _HEADER_DISPLAYS.invalidate_matching(lambda _: True)
    return key


def list_jobs(actor=None, *, display_only=False):
    from design_publish_ad import PREFIX, public as ad_public
    from companion_read_connection import read_connection
    with (read_connection(connect) if display_only else connect()) as conn, conn.cursor() as cur:
        if actor is None:
            cur.execute('''SELECT * FROM product_upload_staff_jobs
                ORDER BY (stage BETWEEN 1 AND 5) DESC, (stage = 0) DESC,
                    (stage = 6) DESC, updated_at DESC LIMIT 20''')
        else:
            cur.execute('''SELECT j.* FROM product_upload_staff_requests r
                JOIN product_upload_staff_jobs j ON j.id=r.job_id WHERE r.requester=%s
                ORDER BY (j.stage BETWEEN 1 AND 5) DESC, (j.stage = 0) DESC,
                (j.stage = 6) DESC, j.updated_at DESC LIMIT 20''', (actor,))
        rows = cur.fetchall()
        # Status remains truthful even when the desktop is disconnected.
        for row in rows:
            if not display_only and 1 <= row['stage'] <= 3 and row['updated_at'] < datetime.now(timezone.utc) - timedelta(minutes=STALL_MINUTES):
                cur.execute('''UPDATE product_upload_staff_jobs SET stage=7,
                    message=%s,updated_at=now() WHERE id=%s AND stage BETWEEN 1 AND 5
                    AND updated_at=%s RETURNING *''',
                    ('No verified progress for 30 minutes. Review the upload and ChatGPT conversation, then explicitly restart or cancel.', row['id'], row['updated_at']))
                stopped = cur.fetchone()
                if stopped:
                    row.update(stopped)
        jobs = [public(row) for row in rows]
        if jobs:
            cur.execute('SELECT value FROM app_settings WHERE key=ANY(%s)',
                        ([PREFIX + job['id'] for job in jobs],))
            ads = {row['value']['upload']: ad_public(row['value']) for row in cur.fetchall()}
            for job in jobs:
                if job['id'] in ads:
                    job['ad'] = ads[job['id']]
            # Upload order must not change while a completed upload's ad waits
            # for Meta. The independent Ads panel owns that unfinished work.
        cur.execute('SELECT seen_at FROM product_upload_desktop WHERE singleton')
        desktop = cur.fetchone()
    online = bool(desktop and desktop['seen_at'] and
                  desktop['seen_at'] > datetime.now(timezone.utc) - timedelta(seconds=95))
    return dict(jobs=jobs, online=online)


def public(row):
    stage = row['stage']
    label, percent = LABELS[stage], PERCENT[stage]
    if stage == 5 and row['storefront']:
        label, percent = 'Shopify published · Upload Companion handling PSD', 96
    cancelled = stage == 7 and row['message'].startswith(CANCELLED)
    stalled = 1 <= stage <= 5 and row['updated_at'] < datetime.now(timezone.utc) - timedelta(minutes=10)
    if cancelled:
        label = 'Cancelled'
    elif stalled:
        label = 'Waiting for verified progress · check conversation' if stage == 5 else 'Taking longer · check companion'
    return dict(id=str(row['id']), dispatch_id=str(row.get('dispatch_id') or row['id']), title=row['title'], stage=stage, label=label,
                percent=percent, detail=row['message'], storefront=row['storefront'],
                updated_at=row['updated_at'].isoformat(), restartable=stage == 7,
                cancellable=stage != 6 and not cancelled, cancelled=cancelled, stalled=stalled)


def cancel(key, user, expected, attempt=None, *, _deleting=False):
    key = UUID(str(key))
    if not isinstance(expected, str) or not expected:
        raise ValueError('Refresh the upload status before cancelling.')
    from os_accounts import can_delete_files
    administrator = can_control_queues(user) or (_deleting and can_delete_files(user))
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute('SELECT intake_id FROM product_upload_staff_jobs WHERE id=%s', (key,))
        selected = cur.fetchone()
        if not selected:
            raise ValueError('This upload is unavailable. Refresh its status.')
        intake = None
        if selected['intake_id']:
            cur.execute('SELECT data FROM product_upload_intakes WHERE id=%s FOR UPDATE', (selected['intake_id'],))
            intake = cur.fetchone()
        cur.execute('''SELECT j.* FROM product_upload_staff_jobs j WHERE j.id=%s AND
            (%s OR EXISTS(SELECT 1 FROM product_upload_staff_requests r
                          WHERE r.job_id=j.id AND r.requester=%s)) FOR UPDATE''',
                    (key, administrator, user['id']))
        job = cur.fetchone()
        if not job:
            raise PermissionError('This upload is unavailable to this account.')
        if job['stage'] == 7 and job['message'].startswith(CANCELLED):
            return public(job)
        changed = (str(job.get('dispatch_id') or job['id']) != attempt if attempt
                   else job['updated_at'] != datetime.fromisoformat(expected))
        if job['stage'] == 6 or changed:
            raise ValueError('This upload changed or already completed. Refresh its status.')
        if intake:
            data = dict(intake['data'])
            data['staff_upload_cancelled'] = str(job.get('dispatch_id') or job['id'])
            cur.execute('UPDATE product_upload_intakes SET data=%s::jsonb,updated_at=now() WHERE id=%s',
                        (json.dumps(data), job['intake_id']))
        cur.execute('''UPDATE product_upload_staff_jobs SET stage=7,message=%s,updated_at=now()
            WHERE id=%s RETURNING *''', (CANCELLED + ' Automatic processing stopped; completed files and listings are retained.', key))
        result = public(cur.fetchone())
    if job['intake_id']:
        from product_upload_jobs import JOBS
        JOBS.cancel(str(job['intake_id']), job['worker_actor'],
                    attempt=str(job.get('dispatch_id') or job['id']))
    LOG.info('staff_upload_cancelled job=%s dispatch=%s previous_stage=%s',
             job['id'], job.get('dispatch_id') or job['id'], job['stage'])
    _HEADER_DISPLAYS.invalidate_matching(lambda _: True)
    return result


def cancel_for_deletion(source, user):
    """A recoverable Review deletion also stops pending uploads of this file."""
    from os_accounts import can_delete_files
    if not can_delete_files(user):
        raise PermissionError('Your account does not have permission to delete Dropbox files.')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM product_upload_staff_jobs WHERE source_id=%s AND stage<>6',
                    (source['id'],))
        jobs = cur.fetchall()
    for job in jobs:
        cancel(job['id'], user, job['updated_at'].isoformat(),
               str(job.get('dispatch_id') or job['id']), _deleting=True)


def delivery(row):
    """Existing installed companions see a new job ID only after an explicit reset."""
    return dict(row, id=row.get('dispatch_id') or row['id']) if row else None


def restart(key, user, expected):
    """Resume verified mapping conflicts; otherwise restart the failed image package."""
    key = UUID(str(key))
    if not isinstance(expected, str) or not expected:
        raise ValueError('Refresh the upload status before restarting.')
    administrator = can_control_queues(user)
    with connect() as conn, conn.cursor() as cur:
        # Match claim locking and intake -> job ordering used by mapping.
        cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute('SELECT intake_id FROM product_upload_staff_jobs WHERE id=%s', (key,))
        selected = cur.fetchone()
        if not selected:
            raise ValueError('This upload is unavailable. Refresh its status.')
        intake = None
        if selected['intake_id']:
            cur.execute('SELECT data FROM product_upload_intakes WHERE id=%s FOR UPDATE', (selected['intake_id'],))
            intake = cur.fetchone()
        cur.execute('''SELECT j.* FROM product_upload_staff_jobs j WHERE j.id=%s AND
            (%s OR EXISTS(SELECT 1 FROM product_upload_staff_requests r
                          WHERE r.job_id=j.id AND r.requester=%s)) FOR UPDATE''',
                    (key, administrator, user['id']))
        job = cur.fetchone()
        if not job:
            raise PermissionError('This upload is unavailable to this account.')
        if job['stage'] != 7 or job['updated_at'] != datetime.fromisoformat(expected):
            raise ValueError('This upload changed or is no longer failed. Refresh its status.')
        if intake and job['message'].startswith('Destination conflict:'):
            data = dict(intake['data'])
            saved = data.get('staff_mapping') or {}
            dispatch = str(job.get('dispatch_id') or job['id'])
            if (saved.get('verified') and saved.get('job') == dispatch
                    and saved.get('source') == data.get('source')
                    and saved.get('source', {}).get('id') == job['source_id']
                    and saved.get('source', {}).get('rev') == job['source_rev']):
                data['staff_mapping_resume'] = dispatch
                cur.execute('UPDATE product_upload_intakes SET data=%s::jsonb,updated_at=now() WHERE id=%s',
                            (json.dumps(data), job['intake_id']))
                cur.execute('''UPDATE product_upload_staff_jobs SET stage=0,message=%s,updated_at=now()
                    WHERE id=%s RETURNING *''', (MAPPING_RESUME, key))
                return public(cur.fetchone())
        result = public(_reset_attempt(cur, job, intake))
    _HEADER_DISPLAYS.invalidate_matching(lambda _: True)
    return result


def _reset_attempt(cur, job, intake):
    """Retire the delivery token; retain product identity and audit receipts."""
    attempt = uuid4()
    if intake:
        data = dict(intake['data'])
        data.pop('staff_upload_cancelled', None)
        history = list(data.get('staff_upload_restarts') or [])
        history.append(dict(previous_dispatch=str(job.get('dispatch_id') or job['id']),
                            reason=job['message'], at=datetime.now(timezone.utc).isoformat(),
                            retired_outputs=dict(mockup_saves=data.get('mockup_saves'),
                                output=(data.get('upload_operation') or {}).get('output'))))
        data['staff_upload_restarts'] = history[-20:]
        data['staff_upload_attempt'] = str(attempt)
        data['staff_full_restart'] = str(attempt)
        from product_upload_source import invalidate
        invalidate({'data': data})
        data.pop('mockup_saves', None)
        data.pop('server_artwork', None)
        data.update(state='Uploaded', reason='')
        data['design_review'] = dict(decision='approved', at=datetime.now(timezone.utc).isoformat())
        task = (data.get('upload_operation') or {}).get('sync_map') or {}
        if task.get('staff_job') == str(job.get('dispatch_id') or job['id']):
            task['staff_job'] = str(attempt)
            task.pop('lease', None)
            task.pop('lease_until', None)
        # Keep source, product identity and completed PSD mapping; the previous
        # output package is audit history only, never a new handoff source.
        data.pop('staff_mapping', None)
        cur.execute('UPDATE product_upload_intakes SET data=%s::jsonb,updated_at=now() WHERE id=%s',
                    (json.dumps(data), job['intake_id']))
    cur.execute('''UPDATE product_upload_staff_jobs SET stage=0,dispatch_id=%s,
        message='Restart requested · regenerating mockups',storefront='',created_at=now(),updated_at=now() WHERE id=%s RETURNING *''', (attempt, job['id']))
    return cur.fetchone()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def pair(user):
    token = secrets.token_urlsafe(32)
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''INSERT INTO product_upload_desktop(singleton,actor_id,token_hash)
            VALUES (true,%s,%s) ON CONFLICT(singleton) DO UPDATE SET token_hash=EXCLUDED.token_hash,
            actor_id=EXCLUDED.actor_id, seen_at=NULL
            WHERE product_upload_desktop.actor_id=EXCLUDED.actor_id RETURNING singleton''', (user['id'], digest(token)))
        if not cur.fetchone():
            raise ValueError('The desktop is already paired to another administrator.')
    return token


def _enabled(cur):
    cur.execute('SELECT value FROM app_settings WHERE key=%s', (CONTROL_KEY,))
    row = cur.fetchone()
    return row is None or row['value'] is not False


def settings(enabled=None):
    """Persist new-upload starts; never interrupt an already claimed upload."""
    with connect() as conn, conn.cursor() as cur:
        if enabled is not None:
            # Use the same lock as desktop_tick so pause and next-job claims
            # have a definite order across all server processes.
            cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
            cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()''',
                (CONTROL_KEY, 'true' if enabled else 'false'))
        return dict(enabled=_enabled(cur))


def desktop_online():
    """Read only the heartbeat; displaying designs must not load/reconcile uploads."""
    from companion_read_connection import read_connection
    with read_connection(connect) as conn, conn.cursor() as cur:
        cur.execute("SELECT seen_at > now()-interval '95 seconds' AS online FROM product_upload_desktop WHERE singleton")
        row = cur.fetchone()
    return bool(row and row['online'])


def header_queue_status():
    from companion_header import enrich_queues
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT
            (SELECT count(*) FROM morning_design_jobs WHERE stage=0) AS design_waiting,
            (SELECT enabled FROM morning_design_control WHERE singleton) AS design_enabled,
            (SELECT count(*) FROM product_upload_staff_jobs WHERE stage=0) AS upload_waiting,
            (SELECT value FROM app_settings WHERE key=%s) AS upload_enabled''', (CONTROL_KEY,))
        row = cur.fetchone()
    from auto_editions_header import snapshot
    return enrich_queues({
        'editions': snapshot(connect),
        'design': dict(waiting=row['design_waiting'], enabled=bool(row['design_enabled'])),
        'upload': dict(waiting=row['upload_waiting'], enabled=row['upload_enabled'] is not False),
    })


def can_control_queues(user):
    import os_accounts
    return os_accounts.is_admin(user) and os_accounts.can_access_page(user, 'Upload Companion')


def desktop_tick(token):
    # Updating the singleton row serializes claims even across server processes.
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''UPDATE product_upload_desktop SET seen_at=now()
            WHERE singleton AND token_hash=%s RETURNING actor_id''', (digest(token),))
        device = cur.fetchone()
        if not device:
            raise PermissionError('Pair this Edge profile in Companion → Companion Queues.')
        cur.execute('SELECT * FROM product_upload_staff_jobs WHERE stage BETWEEN 1 AND 5')
        job = cur.fetchone()
        if not job and _enabled(cur):
            cur.execute('''UPDATE product_upload_staff_jobs SET stage=1,worker_actor=%s,updated_at=now()
                WHERE id=(SELECT id FROM product_upload_staff_jobs WHERE stage=0 ORDER BY created_at,id LIMIT 1)
                RETURNING *''', (device['actor_id'],))
            job = cur.fetchone()
            if job and job['message'] == MAPPING_RESUME:
                cur.execute('SELECT data FROM product_upload_intakes WHERE id=%s', (job['intake_id'],))
                intake = cur.fetchone()
                if not intake or intake['data'].get('staff_mapping_resume') != str(job.get('dispatch_id') or job['id']):
                    raise ValueError('The saved PSD mapping resume receipt changed.')
                cur.execute('''UPDATE product_upload_staff_jobs SET stage=5,
                    message='Resuming verified publication · mapping the original PSD'
                    WHERE id=%s RETURNING *''', (job['id'],))
                job = cur.fetchone()
    return delivery(job)


def worker_job(key, actor):
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT j.* FROM product_upload_staff_jobs j
            JOIN product_upload_desktop d ON d.actor_id=j.worker_actor
            WHERE COALESCE(j.dispatch_id,j.id)=%s AND j.worker_actor=%s AND j.stage BETWEEN 1 AND 5''', (UUID(key), actor))
        return delivery(cur.fetchone())


def advance(key, actor, stage, message='', *, intake=None, storefront='', allowed=None):
    if stage < 1 or stage > 7:
        raise ValueError('Unknown desktop job stage.')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''UPDATE product_upload_staff_jobs SET stage=%s, message=%s, storefront=%s,
            intake_id=COALESCE(intake_id,%s),updated_at=now()
            WHERE COALESCE(dispatch_id,id)=%s AND worker_actor=%s AND stage BETWEEN 1 AND 5 AND stage<=%s
            AND (stage<>%s OR message<>%s OR storefront<>%s OR (intake_id IS NULL AND %s::uuid IS NOT NULL))
            AND (%s::smallint[] IS NULL OR stage=ANY(%s::smallint[]))''',
            (stage, message[:1600], storefront, intake, key, actor, stage, stage, message[:1600], storefront, intake,
             allowed, allowed))


def verify(job):
    """Read confirmed Edition Ops and Shopify state. A submitted prompt is never a success receipt."""
    from pathlib import PurePosixPath
    from product_upload_identity import tag
    from product_upload_intake import Intakes
    from product_upload_mapping import read_edition, tags
    from product_upload_services import Dropbox
    from psd_directory import ROOT
    from psd_mapping_store import STORE
    from shopify_sync import fetch_product_by_shopify_id, shopify_gid

    key = str(job['intake_id'])
    intake = Intakes(connect).read(key, job['worker_actor'])
    if not intake:
        return
    if intake['data'].get('staff_mapping'):
        from product_upload_staff_mapping import run

        def progress(message, storefront):
            advance(job['id'], job['worker_actor'], 5, message, storefront=storefront, allowed=[5])
        try:
            storefront = run(connect, job, intake, progress)
        except (ValueError, PermissionError) as error:
            advance(job['id'], job['worker_actor'], 7, str(error), storefront=job['storefront'], allowed=[5])
            return
        if storefront:
            advance(job['id'], job['worker_actor'], 6, 'Original PSD mapped · handed to Auto Editions',
                    storefront=storefront, allowed=[5])
        return
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT shopify_product_gid FROM product_psd_mappings
                       WHERE dropbox_file_id=%s''', (job['source_id'],))
        matches = cur.fetchall()
    if len(matches) != 1:
        return
    pid = matches[0]['shopify_product_gid']
    mapping = STORE.read_one(pid)
    if (not mapping or not mapping['verified'] or mapping['dropbox_file_id'] != job['source_id'] or
            PurePosixPath(mapping['path']).parent != PurePosixPath(ROOT)):
        return
    if not read_edition(connect, pid):
        return
    product = fetch_product_by_shopify_id(pid)
    data = intake['data']
    target = (data.get('metadata') or {}).get('shopify_product_id')
    correlated = tag(key) in tags(product) and (not target or shopify_gid('Product', target) == pid)
    if not correlated or product['shopify_product_id'] != pid or product['status'] != 'ACTIVE':
        return
    if not product.get('online_store_url'):
        return
    master = Dropbox().metadata_if_present(job['source_id'])
    if (master and master.get('path_display') == mapping['path'] and
            master.get('content_hash') == data['source'].get('content_hash')):
        advance(job['id'], job['worker_actor'], 6, storefront=product['online_store_url'], allowed=[5])


from display_snapshot import Snapshots
_HEADER_DISPLAYS = Snapshots(workers=2, ttl=2, retry=3, max_age=120, limit=32, byte_limit=8_000_000)


def _header_display(user):
    from workspace_display_cache import user_scope
    admin = can_control_queues(user)
    def load():
        result = list_jobs(None if admin else user['id'], display_only=True)
        if admin:
            result['queues'] = header_queue_status()
        return result
    snapshot = _HEADER_DISPLAYS.read((user_scope(user), admin), load)
    return {**(snapshot['value'] or {}), 'display_state': snapshot['state'],
            'checked_at': snapshot['checked_at']}


def requested_status(user, key):
    """Read the exact durable receipt, including jobs outside the header's latest 20."""
    key = UUID(str(key))
    admin = can_control_queues(user)
    from companion_read_connection import read_connection
    with read_connection(connect) as conn, conn.cursor() as cur:
        cur.execute("""SELECT j.* FROM product_upload_staff_jobs j WHERE j.id=%s
            AND (%s OR EXISTS(SELECT 1 FROM product_upload_staff_requests r
                WHERE r.job_id=j.id AND r.requester=%s))""", (key, admin, user['id']))
        row = cur.fetchone()
        if not row:
            raise PermissionError('This upload request is unavailable to this account.')
        cur.execute("SELECT seen_at > now()-interval '95 seconds' AS online FROM product_upload_desktop WHERE singleton")
        device = cur.fetchone()
        enabled = _enabled(cur)
    return dict(job=public(row), online=bool(device and device['online']), enabled=enabled)


async def status_route(request):
    from files_upload_api import _request_user
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user = await run_in_threadpool(_request_user, request, required_page='Design Studio')
        if request.query_params.get('display') == '1':
            result = _header_display(user)
            requested = request.query_params.get('job_id')
            if requested:
                receipt = await run_in_threadpool(requested_status, user, requested)
                prior = next((job for job in result.get('jobs', []) if job['id'] == receipt['job']['id']), {})
                result['jobs'] = [dict(prior, **receipt['job']), *(job for job in result.get('jobs', []) if job['id'] != receipt['job']['id'])]
                result['online'] = receipt['online']
                result['display_state'] = 'ready'
                queues = result.setdefault('queues', {})
                upload = dict(queues.get('upload') or {}, enabled=receipt['enabled'], display=True)
                # A direct receipt can arrive before the cached queue counts.
                # Omit unknown counts rather than manufacturing a zero.
                upload.setdefault('waiting', None)
                queues['upload'] = upload
            from companion_status_payload import response
            return response(result, user, request, HEADERS)
        result = await run_in_threadpool(list_jobs, None if can_control_queues(user) else user['id'])
        if can_control_queues(user):
            result['queues'] = await run_in_threadpool(header_queue_status)
        return JSONResponse(result, headers=HEADERS)
    except Exception as error:
        return failure(error)


async def queue_control_route(request):
    from files_upload_api import _request_user, _same_origin
    from morning_design_queue import settings as design_settings
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        if not request.headers.get('origin') or not _same_origin(request):
            raise PermissionError('Request origin rejected.')
        user = await run_in_threadpool(_request_user, request, required_page='Upload Companion')
        if not can_control_queues(user):
            raise PermissionError('An administrator must control the companion queues.')
        body = await request.json()
        if (not isinstance(body, dict) or body.get('queue') not in ('design', 'upload', 'ads')
                or not isinstance(body.get('enabled'), bool)):
            raise ValueError('Choose a companion queue and Play or Pause.')
        from design_publish_ad import settings as ad_settings
        update = {'design': design_settings, 'upload': settings, 'ads': ad_settings}[body['queue']]
        control = await run_in_threadpool(update, body['enabled'])
        from workspace_display_cache import user_scope
        _HEADER_DISPLAYS.invalidate((user_scope(user), True))
        return JSONResponse({'enabled': control['enabled']}, headers=HEADERS)
    except Exception as error:
        return failure(error)


async def restart_route(request):
    from files_upload_api import _request_user, _same_origin
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        if not request.headers.get('origin') or not _same_origin(request):
            raise PermissionError('Request origin rejected.')
        user = await run_in_threadpool(_request_user, request, required_page='Design Studio')
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Choose a failed upload to restart.')
        action = cancel if request.url.path.endswith('/cancel') else restart
        args = (body.get('id'), user, body.get('updated_at'))
        result = await run_in_threadpool(action, *args, **({'attempt': body.get('dispatch_id')} if action is cancel else {}))
        return JSONResponse({'job': result}, headers=HEADERS)
    except Exception as error:
        return failure(error)


async def pair_route(request):
    from product_upload_api import HEADERS, actor, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user = await actor(request, write=True)
        if not can_control_queues(user):
            raise PermissionError('An administrator must pair the desktop.')
        return JSONResponse({'token': await run_in_threadpool(pair, user)}, headers=HEADERS)
    except Exception as error:
        return failure(error)


def tick(token, event):
    job = desktop_tick(token)
    stop = {}
    try:
        reported = UUID(str(event.get('id')))
    except ValueError:
        reported = None
    if reported:
        with connect() as conn, conn.cursor() as cur:
            cur.execute('''SELECT stage FROM product_upload_staff_jobs
                WHERE COALESCE(dispatch_id,id)=%s''', (reported,))
            previous = cur.fetchone()
        if not previous or previous['stage'] == 7:
            stop = {'stop': {'id': str(reported)}}
    if not job:
        return stop
    key, actor, stage = job['id'], job['worker_actor'], job['stage']
    if str(key) == event.get('id') and stage >= 4:
        state = event.get('state')
        if stage == 4 and state == 'submitted':
            advance(key, actor, 5, allowed=[4])
            stage = 5
        elif stage == 4 and state == 'uncertain':
            # Browser acknowledgement can be lost while ChatGPT publishes. A
            # package-specific ready tag is positive evidence, never a resend.
            from product_upload_staff_mapping import publication_ready
            try:
                if publication_ready(connect, job):
                    advance(key, actor, 5, allowed=[4])
                    stage = 5
            except Exception:
                LOG.warning('Could not reconcile the unconfirmed upload receipt', exc_info=True)
    if stage == 5:
        try:
            verify(job)
        except Exception:
            LOG.warning('Desktop upload verification could not read live state', exc_info=True)
            with connect() as conn, conn.cursor() as cur:
                # An unsuccessful read is not progress and must not reset the timeout.
                cur.execute('''UPDATE product_upload_staff_jobs SET message=%s
                    WHERE COALESCE(dispatch_id,id)=%s AND stage=5''',
                    ('Could not verify publication or PSD mapping. Check the ChatGPT conversation and provider connection; verification will retry.', key))
    current = worker_job(str(key), actor)
    if not current:
        return stop
    # Older installed companions report observation timeouts as blockers. Those
    # are not failed provider operations and must not cancel a running response.
    observation_only = str(event.get('reason') or '').startswith((
        'ChatGPT finished responding, but publication and PSD mapping remain unverified.',
        'The companion cannot read the upload conversation.',
        'The upload conversation tab was closed before publication and PSD mapping were verified.',
    ))
    if str(key) == event.get('id') and current['stage'] == 4 and event.get('state') == 'uncertain':
        advance(key, actor, 4, 'ChatGPT handoff unconfirmed · check the existing conversation; no duplicate prompt will be sent.', allowed=[4])
    if str(key) == event.get('id') and current['stage'] >= 4 and not observation_only and event.get('state') in ('failed', 'blocked'):
        advance(key, actor, 7, str(event.get('reason') or 'ChatGPT stopped without a verified upload result.'), allowed=[4, 5])
        return {'stop': {'id': str(key)}}
    timeout = timedelta(minutes=STALL_MINUTES)
    if (str(key) == event.get('id') and current['stage'] == 4
            and event.get('state') == 'uncertain'
            and current['updated_at'] < datetime.now(timezone.utc) - timeout):
        advance(key, actor, 7,
                'ChatGPT handoff remains unconfirmed after 30 minutes. Queue slot released; '
                'saved files and the existing conversation are retained. Check that conversation '
                'before explicitly restarting; no duplicate prompt was sent.', allowed=[4])
        return {'stop': {'id': str(key)}}
    if current['stage'] < 4 and current['updated_at'] < datetime.now(timezone.utc) - timeout:
        detail = f"{current['message'] or LABELS[stage]} · timed out. Review Product Uploads and the ChatGPT conversation."
        advance(key, actor, 7, detail, storefront=current['storefront'],
                allowed=[stage])
        return {'stop': {'id': str(key)}}
    return dict(stop, job=dict(id=str(key), stage=current['stage']))


async def tick_route(request):
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        authorization = request.headers.get('authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', authorization):
            raise PermissionError('Desktop credential required.')
        event = await request.json()
        if not isinstance(event, dict):
            raise ValueError('Invalid desktop job event.')
        result = await run_in_threadpool(tick, authorization[7:], event)
        return JSONResponse(result, headers=HEADERS)
    except Exception as error:
        return failure(error)


async def ad_tick_route(request):
    from design_publish_ad import tick_route
    return await tick_route(request)


async def ad_file_route(request):
    from ads_companion_transfer import file_route
    return await file_route(request)


async def ad_control_route(request):
    from ads_companion_controls import route
    return await route(request)


async def ad_quick_add_route(request):
    from ads_companion_quick_add import route
    return await route(request)


ROUTES = (
    ('/api/staff-product-uploads/ad-control', ad_control_route, ('POST',)),
    ('/api/staff-product-uploads/ad-quick-add', ad_quick_add_route, ('GET','POST')),
    ('/api/staff-product-uploads/ad-file', ad_file_route, ('POST',)),
    ('/api/staff-product-uploads/cancel', restart_route, ('POST',)),
    ('/api/staff-product-uploads/ad-tick', ad_tick_route, ('POST',)),
    ('/api/staff-product-uploads/restart', restart_route, ('POST',)),
    ('/api/staff-product-uploads/status', status_route, ('GET',)),
    ('/api/staff-product-uploads/queue-control', queue_control_route, ('POST',)),
    ('/api/staff-product-uploads/pair', pair_route, ('POST',)),
    ('/api/staff-product-uploads/tick', tick_route, ('POST',)),
)
