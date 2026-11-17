"""Durable staff requests, restricted to the paired desktop and exact artwork."""
import hashlib
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


def connect():
    from product_upload_api import connect as upload_connect
    return upload_connect()


def enqueue(user, source, title, sport):
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
    return key


def list_jobs(actor=None):
    with connect() as conn, conn.cursor() as cur:
        if actor is None:
            cur.execute('''SELECT * FROM product_upload_staff_jobs
                ORDER BY (stage < 6) DESC, updated_at DESC LIMIT 20''')
        else:
            cur.execute('''SELECT j.* FROM product_upload_staff_requests r
                JOIN product_upload_staff_jobs j ON j.id=r.job_id WHERE r.requester=%s
                ORDER BY (j.stage BETWEEN 1 AND 5) DESC, (j.stage = 0) DESC,
                j.updated_at DESC LIMIT 20''', (actor,))
        jobs = [public(row) for row in cur.fetchall()]
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
    return dict(id=str(row['id']), title=row['title'], stage=stage, label=label,
                percent=percent, detail=row['message'], storefront=row['storefront'],
                updated_at=row['updated_at'].isoformat())


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
    return job


def worker_job(key, actor):
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT j.* FROM product_upload_staff_jobs j
            JOIN product_upload_desktop d ON d.actor_id=j.worker_actor
            WHERE j.id=%s AND j.worker_actor=%s AND j.stage BETWEEN 1 AND 5''', (UUID(key), actor))
        return cur.fetchone()


def advance(key, actor, stage, message='', *, intake=None, storefront='', allowed=None):
    if stage < 1 or stage > 7:
        raise ValueError('Unknown desktop job stage.')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''UPDATE product_upload_staff_jobs SET stage=%s, message=%s, storefront=%s,
            intake_id=COALESCE(intake_id,%s),updated_at=now()
            WHERE id=%s AND worker_actor=%s AND stage BETWEEN 1 AND 5 AND stage<=%s
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
        return JSONResponse(await run_in_threadpool(list_jobs, user['id']), headers=HEADERS)
    except Exception as error:
        return failure(error)


async def pair_route(request):
    import os_accounts
    from product_upload_api import HEADERS, actor, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user = await actor(request, write=True)
        if not os_accounts.is_admin(user) or not os_accounts.can_access_page(user, 'Upload Companion'):
            raise PermissionError('An administrator must pair the desktop.')
        return JSONResponse({'token': await run_in_threadpool(pair, user)}, headers=HEADERS)
    except Exception as error:
        return failure(error)


def tick(token, event):
    job = desktop_tick(token)
    if not job:
        return {}
    key, actor, stage = job['id'], job['worker_actor'], job['stage']
    if str(key) == event.get('id') and stage >= 4:
        state = event.get('state')
        if stage == 4 and state == 'submitted':
            advance(key, actor, 5, allowed=[4])
            stage = 5
        elif state in ('failed', 'uncertain', 'blocked'):
            advance(key, actor, 7, str(event.get('reason') or 'ChatGPT needs attention.'), allowed=[4, 5])
            return {}
    if stage == 5:
        try:
            verify(job)
        except Exception:
            LOG.warning('Desktop upload verification could not read live state', exc_info=True)
    current = worker_job(str(key), actor)
    if not current:
        return {}
    timeout = timedelta(hours=2 if stage == 5 else 1)
    if current['updated_at'] < datetime.now(timezone.utc) - timeout:
        detail = f"{current['message'] or LABELS[stage]} · timed out. Review Product Uploads and the ChatGPT conversation."
        advance(key, actor, 7, detail, storefront=current['storefront'],
                allowed=[stage])
        return {}
    return dict(job=dict(id=str(key), stage=stage))


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


ROUTES = (
    ('/api/staff-product-uploads/status', status_route, ('GET',)),
    ('/api/staff-product-uploads/pair', pair_route, ('POST',)),
    ('/api/staff-product-uploads/tick', tick_route, ('POST',)),
)
