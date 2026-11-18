"""Lazy refresh shortlist and explicit handoff to the existing design queue."""
import json
import re
from uuid import uuid5, NAMESPACE_URL

from supabase_backend import connect

KEY = 'home_refresh_manual_products'
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


def listing(query='', offset=0, all_designs=False):
    verified, freshness = (set(), None) if all_designs else companion()
    with connect() as conn, conn.cursor() as cur:
        rows = catalog(cur)
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (KEY,))
        saved = cur.fetchone()
        manual = set(saved['value'] if saved else [])
        cur.execute("SELECT id,stage FROM morning_design_jobs WHERE section='refresh'")
        jobs = {str(r['id']): r['stage'] for r in cur.fetchall()}
    rows = [dict(r, stage=jobs.get(job_id(r['product_id']))) for r in rows
            if (all_designs or r['product_id'] not in verified or r['product_id'] in manual)
            and query.casefold() in (r['title'] + ' ' + r['product_id']).casefold()]
    return dict(rows=rows[offset:offset+PAGE_SIZE], total=len(rows),
                next_offset=offset+PAGE_SIZE if offset+PAGE_SIZE < len(rows) else None,
                freshness=freshness)


def change(pid, action):
    pid = product_id(pid)
    if action not in ('add', 'enqueue'):
        raise ValueError('Unknown action.')
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
        cur.execute('SELECT stage FROM morning_design_jobs WHERE id=%s FOR UPDATE', (key,))
        existing = cur.fetchone()
        if existing:
            return dict(added=False, stage=existing['stage'])
        from home_design_refresh import _refresh_prompt
        from sports_sales_calendar import sydney_date
        prompt = _refresh_prompt(dict(row, suggestion='Research a complete redesign for this selected existing design.',
            evidence='Selected from Designs to Refresh. Companion verification is a technical status, not an artwork quality judgement.'),
            'https://www.sportscaveshop.com/products/' + row['handle'])
        prompt = 'SPORTS CAVE EXISTING DESIGN REFRESH\n' + prompt + (
            f'\nInclude morning_design_job_id = "{key}" in the final .upload.json handoff. '
            'Save to Design Studio Review only; do not publish or alter the live product.\n')
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
            result = await run_in_threadpool(listing, query, offset, params.get('all') == '1')
        return JSONResponse(result, headers=headers)
    except (PermissionError, FilesUploadError):
        return JSONResponse({'error': 'Owner access required.'}, status_code=403, headers=headers)
    except ValueError as error:
        return JSONResponse({'error': str(error)}, status_code=400, headers=headers)
    except Exception:
        return JSONResponse({'error': 'Designs are temporarily unavailable. Please retry.'}, status_code=503, headers=headers)
