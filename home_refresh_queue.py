"""Lazy refresh shortlist and explicit handoff to the existing design queue."""
import json
import logging
import re
from uuid import uuid4, uuid5, NAMESPACE_URL

from supabase_backend import connect

KEY = 'home_refresh_manual_products'
SEED_KEY = 'home_refresh_initial_products'
PAGE_SIZE = 40


def product_id(value):
    value = str(value).removeprefix('gid://shopify/Product/')
    if not re.fullmatch(r'[0-9]{1,20}', value):
        raise ValueError('Invalid design ID.')
    return value


def job_id(pid):
    return str(uuid5(NAMESPACE_URL, 'sports-cave-refresh:' + product_id(pid)))


def catalog(cur):
    cur.execute('''SELECT shopify_product_id, title, handle FROM shopify_products
        WHERE lower(status) = 'active' ORDER BY lower(title), shopify_product_id LIMIT 10001''')
    rows = cur.fetchall()
    if len(rows) > 10000:
        raise ValueError('Catalogue exceeds the supported size.')
    return [dict(product_id=product_id(r['shopify_product_id']), title=r['title'] or r['handle'],
                 handle=r['handle']) for r in rows if r['handle']]


def companion():
    from worker_health_cache import snapshot
    from worker_health import Health
    data = snapshot(Health(connect))
    return {product_id(j['id']) for j in data['jobs'] if j['completed']}, data['freshness']


def listing(query='', offset=0, all_designs=False, verify=False):
    freshness = None
    with connect() as conn, conn.cursor() as cur:
        rows = catalog(cur)
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (SEED_KEY,))
        initial = cur.fetchone()
    if not all_designs and initial is None:
        # Populate once from verified evidence; never seed from an unavailable snapshot.
        verified, freshness = companion()
        seed = [r['product_id'] for r in rows if r['product_id'] not in verified]
        with connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT DO NOTHING",
                        (SEED_KEY, json.dumps(seed)))
            cur.execute('SELECT value FROM app_settings WHERE key=%s', (SEED_KEY,))
            initial = cur.fetchone()
    selected = set(initial['value'] if initial else [])
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (KEY,))
        saved = cur.fetchone()
        manual = set(saved['value'] if saved else [])
        cur.execute("SELECT id,stage,file_id,file_rev,file_path FROM morning_design_jobs WHERE section='refresh'")
        jobs = {str(r['id']): dict(r) for r in cur.fetchall()}
    rows = [dict(r, stage=(jobs.get(job_id(r['product_id'])) or {}).get('stage')) for r in rows
            if (all_designs or r['product_id'] in selected or r['product_id'] in manual)
            and query.casefold() in (r['title'] + ' ' + r['product_id']).casefold()]
    page = rows[offset:offset+PAGE_SIZE]
    from design_deletion_status import snapshot
    observed = snapshot([jobs[job_id(row['product_id'])] for row in page
                         if not all_designs and job_id(row['product_id']) in jobs], set(), refresh=True, force=verify)
    for row in page:
        job = jobs.get(job_id(row['product_id']))
        row['can_requeue'] = bool(job and job['id'] in observed['deleted'])
    result = dict(rows=page, total=len(rows),
                  next_offset=offset+PAGE_SIZE if offset+PAGE_SIZE < len(rows) else None,
                  freshness=freshness)
    if observed['state'] in ('loading', 'busy', 'stale'):
        result.update(state='loading', message='Checking deleted refresh artwork…')
    return result


def change(pid, action):
    pid = product_id(pid)
    if action not in ('add', 'enqueue'):
        raise ValueError('Unknown action.')
    # Dropbox reads must not hold the desktop claim lock. Recheck this snapshot
    # under that lock before authorising a new attempt.
    observed = None
    if action == 'enqueue':
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM morning_design_jobs WHERE id=%s AND section='refresh'", (job_id(pid),))
            previous = cur.fetchone()
        if previous:
            from morning_design_queue import _deleted_designs
            if previous['id'] in _deleted_designs([previous], set(), exact_live_identity=True):
                observed = dict(previous)
    with connect() as conn, conn.cursor() as cur:
        # Serialize queue clicks with existing companion claims.
        cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
        row = next((r for r in catalog(cur) if r['product_id'] == pid), None)
        if not row:
            raise ValueError('This active design is no longer in the catalogue.')
        cur.execute("INSERT INTO app_settings(key,value,updated_at) VALUES (%s,'[]'::jsonb,now()) ON CONFLICT DO NOTHING", (KEY,))
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (KEY,))
        manual = set(cur.fetchone()['value'])
        manual.add(pid)
        cur.execute('UPDATE app_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s', (json.dumps(sorted(manual)), KEY))
        if action == 'add':
            return dict(added=True)
        key = job_id(pid)
        cur.execute('SELECT * FROM morning_design_jobs WHERE id=%s FOR UPDATE', (key,))
        existing = cur.fetchone()
        if existing and (observed is None or dict(existing) != observed):
            return dict(added=False, stage=existing['stage'])
        receipt = str(uuid4()) if existing else key
        from home_design_refresh import _refresh_prompt
        from sports_sales_calendar import sydney_date
        prompt = _refresh_prompt(dict(row, suggestion='Research a complete redesign for this selected existing design.',
            evidence='Selected from Designs to Refresh. Companion verification is a technical status, not an artwork quality judgement.'),
            'https://www.sportscaveshop.com/products/' + row['handle'])
        prompt = 'SPORTS CAVE EXISTING DESIGN REFRESH\n' + prompt + (
            f'\nInclude morning_design_job_id = "{receipt}" in the final .upload.json handoff. '
            'Save to Design Studio Review only; do not publish or alter the live product.\n')
        if existing:
            prompt += f'\nQueue retry receipt: {receipt}\nQueue output receipt: {receipt}\n'
            cur.execute('''UPDATE morning_design_jobs SET stage=0,prompt=%s,title=%s,edition_date=%s,
                message='',chat_url='',file_id='',file_rev='',file_path='',updated_at=now() WHERE id=%s''',
                (prompt, row['title'], sydney_date(), key))
        else:
            cur.execute('''INSERT INTO morning_design_jobs(id,edition_date,section,title,prompt)
                VALUES(%s,%s,'refresh',%s,%s) ON CONFLICT(id) DO NOTHING''',
                (key, sydney_date(), row['title'], prompt))
        return dict(added=True, stage=0)


async def api(request):
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    from files_upload_api import _request_user, _same_origin, FilesUploadError
    import os_accounts
    headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
    try:
        if request.method == 'POST' and (not request.headers.get('origin') or not _same_origin(request)):
            raise PermissionError('Invalid request origin.')
        user = await run_in_threadpool(_request_user, request, required_page='dashboard')
        if not os_accounts.is_reporting_owner(user):
            raise PermissionError('Owner access required.')
        params = request.query_params
        if request.method == 'POST':
            result = await run_in_threadpool(change, params.get('id', ''), params.get('action', ''))
        else:
            offset = int(params.get('offset', '0'))
            query = params.get('q', '')
            if not 0 <= offset <= 10000 or len(query) > 160:
                raise ValueError('Invalid search.')
            result = await run_in_threadpool(listing, query, offset, params.get('all') == '1', params.get('verify') == '1')
        return JSONResponse(result, headers=headers)
    except (PermissionError, FilesUploadError):
        return JSONResponse({'error': 'Owner access required.'}, status_code=403, headers=headers)
    except TimeoutError:
        if request.method == 'GET':
            return JSONResponse({'state': 'loading', 'retry_after_ms': 1000,
                                 'message': 'Checking companion verificationâ€¦'},
                                status_code=202, headers={**headers, 'Retry-After': '1'})
        return JSONResponse({'error': 'Queue request timed out. Please retry.'}, status_code=503, headers=headers)
    except ValueError as error:
        return JSONResponse({'error': str(error)}, status_code=400, headers=headers)
    except Exception as error:
        logging.getLogger(__name__).warning('home_refresh_queue_failed type=%s', type(error).__name__)
        return JSONResponse({'error': 'Designs are temporarily unavailable. Please retry.'}, status_code=503, headers=headers)
