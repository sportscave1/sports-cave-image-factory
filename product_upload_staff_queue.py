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


def connect():
    from product_upload_api import connect as upload_connect
    return upload_connect()


def enqueue(user, source, title, sport, *, ad_country=None):
    if ad_country is not None:
        import design_publish_ad as ad
        sport, ad_country = ad.check_request(user, sport, ad_country)
    from design_review_page import final_psd
    if not final_psd(source) or not source.get('id') or not source.get('rev'):
        raise ValueError('Choose a current PSD from Design Studio Review.')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''INSERT INTO product_upload_staff_jobs(id,source_id,source_rev,title,sport)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT(source_id,source_rev) DO UPDATE SET source_id=EXCLUDED.source_id
            RETURNING id''', (uuid4(), source['id'], source['rev'], title, sport))
        key = cur.fetchone()['id']
        cur.execute('''INSERT INTO product_upload_staff_requests(requester,job_id)
            VALUES (%s,%s) ON CONFLICT DO NOTHING''', (user['id'], key))
        if ad_country is not None:
            ad.enqueue(cur, key, user['id'], sport, ad_country)
    return key


def list_jobs(actor=None):
    from design_publish_ad import PREFIX, public as ad_public
    with connect() as conn, conn.cursor() as cur:
        if actor is None:
            cur.execute('''SELECT * FROM product_upload_staff_jobs
                ORDER BY (stage < 6) DESC, updated_at DESC LIMIT 20''')
        else:
            cur.execute('''SELECT j.* FROM product_upload_staff_requests r
                JOIN product_upload_staff_jobs j ON j.id=r.job_id WHERE r.requester=%s
                ORDER BY (j.stage BETWEEN 1 AND 5) DESC, (j.stage = 0) DESC,
                j.updated_at DESC LIMIT 20''', (actor,))
        rows = cur.fetchall()
        # Status remains truthful even when the desktop is disconnected.
        for row in rows:
            if 1 <= row['stage'] <= 5 and row['updated_at'] < datetime.now(timezone.utc) - timedelta(minutes=STALL_MINUTES):
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
            jobs.sort(key=lambda job: job['stage'] >= 6 and not (job.get('ad') or {}).get('active'))
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
        label = 'Needs attention · no verified progress for 10 minutes'
    return dict(id=str(row['id']), title=row['title'], stage=stage, label=label,
                percent=percent, detail=row['message'], storefront=row['storefront'],
                updated_at=row['updated_at'].isoformat(), restartable=stage == 7,
                cancellable=stage != 6 and not cancelled, cancelled=cancelled, stalled=stalled)


def cancel(key, user, expected):
    key = UUID(str(key))
    if not isinstance(expected, str) or not expected:
        raise ValueError('Refresh the upload status before cancelling.')
    administrator = can_control_queues(user)
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
        if job['stage'] == 6 or job['updated_at'] != datetime.fromisoformat(expected):
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
        JOBS.cancel(str(job['intake_id']), job['worker_actor'])
    return result


def delivery(row):
    """Existing installed companions see a new job ID only after an explicit reset."""
    return dict(row, id=row.get('dispatch_id') or row['id']) if row else None


def restart(key, user, expected):
    """Restart Publish now for this failed snapshot, regenerating its web-image package."""
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
            message='Restart requested · regenerating mockups',updated_at=now() WHERE id=%s RETURNING *''', (attempt, key))
        return public(cur.fetchone())


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


def header_queue_status():
    from companion_header import enrich_queues
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT
            (SELECT count(*) FROM morning_design_jobs WHERE stage=0) AS design_waiting,
            (SELECT enabled FROM morning_design_control WHERE singleton) AS design_enabled,
            (SELECT count(*) FROM product_upload_staff_jobs WHERE stage=0) AS upload_waiting,
            (SELECT value FROM app_settings WHERE key=%s) AS upload_enabled''', (CONTROL_KEY,))
        row = cur.fetchone()
    return enrich_queues({
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
            raise PermissionError('Pair this Edge profile in Developer → Upload Companion.')
        cur.execute('SELECT * FROM product_upload_staff_jobs WHERE stage BETWEEN 1 AND 5')
        job = cur.fetchone()
        if not job and _enabled(cur):
            cur.execute('''UPDATE product_upload_staff_jobs SET stage=1,worker_actor=%s,updated_at=now()
                WHERE id=(SELECT id FROM product_upload_staff_jobs WHERE stage=0 ORDER BY created_at,id LIMIT 1)
                RETURNING *''', (device['actor_id'],))
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


async def status_route(request):
    from files_upload_api import _request_user
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user = await run_in_threadpool(_request_user, request, required_page='Design Studio')
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
        result = await run_in_threadpool(action, body.get('id'), user, body.get('updated_at'))
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
        if previous and previous['stage'] == 7:
            stop = {'stop': {'id': str(reported)}}
    if not job:
        return stop
    key, actor, stage = job['id'], job['worker_actor'], job['stage']
    if str(key) == event.get('id') and stage >= 4:
        state = event.get('state')
        if stage == 4 and state == 'submitted':
            advance(key, actor, 5, allowed=[4])
            stage = 5
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
    if str(key) == event.get('id') and current['stage'] >= 4 and event.get('state') in ('failed', 'uncertain', 'blocked', 'stalled'):
        advance(key, actor, 7, str(event.get('reason') or 'ChatGPT stopped without a verified upload result.'), allowed=[4, 5])
        return {'stop': {'id': str(key)}}
    timeout = timedelta(minutes=STALL_MINUTES)
    if current['updated_at'] < datetime.now(timezone.utc) - timeout:
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


ROUTES = (
    ('/api/staff-product-uploads/cancel', restart_route, ('POST',)),
    ('/api/staff-product-uploads/ad-tick', ad_tick_route, ('POST',)),
    ('/api/staff-product-uploads/restart', restart_route, ('POST',)),
    ('/api/staff-product-uploads/status', status_route, ('GET',)),
    ('/api/staff-product-uploads/queue-control', queue_control_route, ('POST',)),
    ('/api/staff-product-uploads/pair', pair_route, ('POST',)),
    ('/api/staff-product-uploads/tick', tick_route, ('POST',)),
)
