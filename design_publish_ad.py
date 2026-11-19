"""Design Studio's opt-in Instant Experience handoff and posting queue."""
import hashlib
import json
import logging
import re
import time
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from product_upload_staff_queue import connect, digest

PROJECT = 'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project'
PREFIX = 'design_publish_ad:'
CONTROL_KEY = PREFIX + 'enabled'
HEARTBEAT_KEY = PREFIX + 'desktop'
CHAT = re.compile(r'https://chatgpt\.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-sports-cave-meta-ads)?/c/[a-f0-9-]{36}')
COUNTRIES = {'Australia': ('AUS', 'AU', 'Australia'), 'USA': ('USA', 'US', 'United States'),
             'UK': ('UK', 'GB', 'United Kingdom'), 'Canada': ('CAN', 'CA', 'Canada'),
             'New Zealand': ('NZ', 'NZL', 'New Zealand')}
COVERS = {idea['id']: idea['scene_name'].lower().replace(' ', '-') + '.jpg'
          for idea in INSTANT_EXPERIENCE_CONCEPTS}
LABELS = {'waiting': 'Waiting for the published product', 'preparing': 'Preparing the verified mockup',
          'opening': 'Opening Meta Ads in ChatGPT',
          'generating': 'Waiting for ad copy and three covers', 'posting': 'Creating the Meta campaign',
          'complete': 'Ads created · paused for review', 'failed': 'Ad needs attention', 'cancelled': 'Cancelled'}
LOG = logging.getLogger(__name__)


def country_name(value):
    value = str(value or '').strip().casefold()
    return next((name for name, aliases in COUNTRIES.items()
                 if value in {label.casefold() for label in (name, *aliases)}), '')


def primary_country(details):
    from home_brief_calendar import HISTORY_PREFIX, display_markets
    from morning_design_queue import identity
    try:
        job = UUID(details.get('morning_design_job_id') or '')
    except ValueError:
        return country_name(details.get('primary_market'))
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT j.edition_date::text AS edition_date, j.section, a.value FROM morning_design_jobs j
            LEFT JOIN app_settings a ON a.key=%s || j.edition_date::text WHERE j.id=%s''',
                    (HISTORY_PREFIX, job))
        row = cur.fetchone()
    if row and row['value']:
        for item in row['value'].get(row['section'], []):
            if identity(str(row['edition_date']), row['section'], item) == str(job):
                markets = display_markets(item)
                return country_name(markets[0] if markets else '')
    return country_name(details.get('primary_market'))


def check_request(user, sport, country):
    from os_accounts import can_access_page
    from sports_categories import normalize_sport_category
    if not all(can_access_page(user, page) for page in ('Ads', 'Posting', 'Files')):
        raise ValueError('Publish + ad requires access to Ads, Posting and Files.')
    country = country_name(country)
    sport = normalize_sport_category(sport)
    if not country or not sport or sport == 'Other':
        raise ValueError('Choose a supported country and sport for the ad.')
    return sport, country


def enqueue(cur, upload, requester, sport, country):
    key = PREFIX + str(upload)
    payload = dict(upload=str(upload), requester=str(requester), sport=sport, country=country, stage='waiting')
    cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
        ON CONFLICT DO NOTHING''', (key, json.dumps(payload)))
    cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
    existing = cur.fetchone()['value']
    if existing['country'] != country or existing['sport'] != sport:
        raise ValueError('This PSD revision already has an ad job with different targeting.')


def public(value):
    if not value:
        return None
    return dict(label=('Waiting for Meta catalogue' if value.get('catalog_retry') and value['stage']=='generating' else LABELS[value['stage']]), detail=value.get('detail', ''),
                active=value['stage'] not in ('complete', 'failed', 'cancelled'),
                posting_id=value.get('posting_id'))


def _enabled(cur):
    cur.execute('SELECT value FROM app_settings WHERE key=%s', (CONTROL_KEY,))
    row = cur.fetchone()
    return row is None or row['value'] is not False


def settings(enabled=None):
    with connect() as conn, conn.cursor() as cur:
        if enabled is not None:
            cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
            cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()""",
                        (CONTROL_KEY, json.dumps(enabled)))
        return {'enabled': _enabled(cur)}


def dashboard():
    from companion_read_connection import read_connection
    with read_connection(connect) as conn, conn.cursor() as cur:
        enabled = _enabled(cur)
        cur.execute("""SELECT updated_at > now()-interval '95 seconds' AS online
                       FROM app_settings WHERE key=%s""", (HEARTBEAT_KEY,))
        status = cur.fetchone()
        cur.execute("""SELECT a.value - 'prompt' - 'result' AS value, a.updated_at,
            (SELECT value->>'action' FROM app_settings WHERE key='ads_job_control:' || (a.value->>'upload')) AS control,
            COALESCE(j.title, a.value->'result'->>'product_name') AS title,
            CASE WHEN a.value->>'source'='new_ads' THEN 6 ELSE j.stage END AS upload_stage
            FROM app_settings a LEFT JOIN product_upload_staff_jobs j ON a.key=%s || j.id::text
            WHERE (j.id IS NOT NULL OR (a.key LIKE %s AND a.value->>'source'='new_ads'))
              AND NOT EXISTS (SELECT 1 FROM app_settings c WHERE c.key='ads_job_control:' || (a.value->>'upload') AND c.value->>'action'='delete')
            ORDER BY CASE a.value->>'stage'
                WHEN 'preparing' THEN 0 WHEN 'opening' THEN 0 WHEN 'generating' THEN 0 WHEN 'posting' THEN 0
                WHEN 'waiting' THEN 1 ELSE 2 END,
                CASE WHEN a.value->>'stage'='waiting' THEN a.updated_at END,
                a.updated_at DESC, a.key LIMIT 100""", (PREFIX, PREFIX + '%'))
        jobs = []
        for row in cur.fetchall():
            value = row['value']
            if row['control']=='delete': continue
            if row['control']=='cancel':
                value.update(stage='cancelled',detail='Automation stopped. Already-started Meta operations must be reviewed in Posting.')
            entry = dict(public(value), id=value['upload'], updated_at=row['updated_at'].isoformat(),
                         title=row['title'], country=value['country'], sport=value['sport'],
                         stage=value['stage'], chat_url=value.get('chat_url'), targeting=value.get('targeting'),
                         can_play=value['stage']!='complete', can_cancel=value['stage'] not in ('complete','cancelled'),
                         resumable=value['stage'] in ('failed','generating') and bool(value.get('chat_url') and value.get('folder')) and not value.get('posting_id'))
            if value['stage'] == 'waiting' and row['upload_stage'] == 6:
                entry['label'] = 'Ready for the ad queue' if enabled else 'Ready · queue paused'
            elif value['stage'] == 'waiting' and row['upload_stage'] == 7:
                entry['label'] = 'Product upload needs attention'
            jobs.append(entry)
        return {'online': bool(status and status['online']), 'enabled': enabled, 'jobs': jobs}


def write(key, value):
    with connect() as conn, conn.cursor() as cur:
        cur.execute('UPDATE app_settings SET value=%s::jsonb, updated_at=now() WHERE key=%s',
                    (json.dumps(value), key))


def _source_token(job):
    return hashlib.sha256(('design-publish-ad:' + job).encode()).hexdigest()


def _posting_id(job):
    return str(uuid5(NAMESPACE_URL, 'sports-cave-design-publish-ad:' + job))


def _prompt(result, saved, folder, job):
    black = saved['originals']['black-frame']
    black_path = saved['folder'] + '/' + black['filename']
    preview = ('https://www.dropbox.com/home' + quote(saved['folder'], safe='/')
               + '?' + urlencode({'preview': black['filename']}))
    reference = f"""First retrieve the original black-frame WebP through connected Dropbox, by file ID
{black['file_id']}, revision {black['revision']}, and exact path {json.dumps(black_path, ensure_ascii=False)}.
Expected size: {black['size_bytes']} bytes. Dropbox content hash: {black['content_hash']}.
Dropbox preview for identification: {preview}
Use that exact file as the image reference for all three covers, following the artwork
preservation rules below. A storefront image, preview or other frame is not a substitute."""
    return delivery_prompt(result, reference, folder, job)


def delivery_prompt(result, reference, folder, job):
    outputs = '\n'.join(f'- {idea["scene_name"]}: {folder}/{COVERS[idea["id"]]}'
                        for idea in INSTANT_EXPERIENCE_CONCEPTS)
    return f"""Sports Cave automatic ad job {job}

{reference}

Apply the New Ads Instant Experience brief below. Generate the three full-resolution covers
and actual UTF-8 ad_copy.csv. Return all FOUR original downloadable files together in your
final response, with exactly these filenames (the companion will save them to these paths):
{outputs}
- CSV: {folder}/ad_copy.csv

Return actual JPEGs under the given .jpg filenames, not preview thumbnails or contact sheets.
Keep the current CSV format. Do not add image URLs to the CSV. Do not publish Meta ads or
operate the Ads app. The companion downloads these four attachments, saves and verifies them
in the job's Dropbox folder, selects verified targeting, and submits the existing posting job.
Once all four downloadable files are present, emit SC_AD_READY: {job}.
If a required step is blocked, finish independent work and end with SC_AD_BLOCKED:
followed by the exact incomplete checkpoint. Once delivery is verified, report completion.

{result['master_prompt']}

Before the final response, verify all four downloadable attachments are present above.
"""


def _prepare(value, job):
    if value.get('source') == 'new_ads':
        from ads_companion_queue import prepare
        return prepare(value)
    import ads_page
    from ads_auto_post import destination
    from product_upload_intake import Intakes
    from product_upload_mapping import read_edition
    from product_upload_services import Dropbox
    from product_upload_staff_mapping import verified_package
    from shopify_sync import fetch_product_by_shopify_id

    intake = Intakes(connect).read(str(job['intake_id']), job['worker_actor'])
    if not intake:
        raise ValueError('The exact Product Uploads intake is missing.')
    saved = verified_package(intake, value['upload'])
    info = intake['data']
    pid = info.get('product_gid')
    if not pid or not read_edition(connect, pid):
        raise ValueError('The published product could not be matched in Edition Ops.')
    product = fetch_product_by_shopify_id(pid)
    if (not product or product['shopify_product_id'] != pid or product['status'] != 'ACTIVE'
            or not product.get('online_store_url') or product['online_store_url'] != job['storefront']):
        raise ValueError('The live Shopify listing does not match this upload.')
    dbx = Dropbox()
    black = saved['originals']['black-frame']
    path = saved['folder'] + '/' + black['filename']
    current = dbx.metadata_if_present(path)
    if not current or any(current.get(k) != black[v] for k, v in
            (('id', 'file_id'), ('rev', 'revision'), ('size', 'size_bytes'), ('content_hash', 'content_hash'))):
        raise ValueError('The black-frame mockup changed after the Product Uploads receipt.')
    metadata = info.get('metadata') or {}
    result = ads_page.build_ads_result_record(
        product['title'], value['sport'], value['country'], 'Instant Experience',
        product_id=pid, product_url=product['online_store_url'],
        variation_token=_source_token(value['upload'])[:16],
        product_metadata={'product_sport': value['sport'], **{k: metadata[k] for k in
                          ('athletes', 'teams', 'league') if k in metadata}})
    root = dbx.context['root_path']
    folder = destination(dbx.api, root, result) + '/publish-' + value['upload']
    dbx.api.ensure_folder_path(dbx.token, folder, root_path=root)
    return dict(stage='opening', result=result, folder=folder,
                handle=product.get('handle') or PurePosixPath(job['storefront'].split('?')[0]).name,
                prompt=_prompt(result, saved, folder, value['upload']))


def _selected_product_set(rows, sport):
    from ads_target_relevance import tokens
    from sports_categories import normalize_sport_category
    for suffix in (('popular', 'set'), ('popular',), ('wall', 'art')):
        matching = [row for row in rows if row.get('id') and
                    (words := tokens(row.get('name')))[:-len(suffix)] and
                    words[-len(suffix):] == suffix and
                    normalize_sport_category(' '.join(words[:-len(suffix)])) == sport]
        if len(matching) == 1:
            return str(matching[0]['id'])
        if matching:
            raise ValueError(f'Multiple {sport} catalog sets match. Choose the correct set in Posting.')
    raise ValueError(f'No {sport} Popular Set or {sport} Wall Art set was found in the configured catalog.')


def _selected_audience(posting, refs, result):
    from ads_target_relevance import rank_relevant_meta_options
    options = posting._audience_options(refs)
    from posting_import_csv import canonical_posting_country
    country = canonical_posting_country(result['country'])
    countries = {row['id']: ((row.get('targeting') or {}).get('geo_locations') or {}).get('countries') or []
                 for row in refs.get('saved_audiences') or ()}
    code = posting.COUNTRY_META_CODES[country]
    matching = [row for row in options if row['type'] != 'broad' and
                (not countries.get(row['id']) or code in countries[row['id']])]
    ranked = rank_relevant_meta_options(matching, product_title=result['product_name'],
                                        sport=result['category'], id_key='key')['options']
    return ranked[0] if ranked else options[0]


def _download(provider, meta, size_limit):
    if not (0 < meta.get('size', 0) <= size_limit):
        raise ValueError(f"{meta['name']} is empty or exceeds the upload limit.")
    actual, response = provider.api.get_psd_file_response(provider.token, meta['id'], meta['rev'])
    try:
        if any(actual.get(k) != meta[k] for k in ('size', 'content_hash', 'path_display')):
            raise ValueError('The Dropbox ad files changed during verification.')
        data = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            data.extend(chunk)
            if len(data) > meta['size']:
                raise ValueError('Dropbox returned more data than the saved ad file.')
        if len(data) != meta['size']:
            raise RuntimeError('Dropbox returned an incomplete ad file.')
        return bytes(data)
    finally:
        response.close()


def _post_request(value):
    import ads_direct_post
    import ads_image_workflow
    import ads_page
    import ads_posting_page as posting
    from posting_import_csv import canonical_posting_country
    from product_upload_services import Dropbox

    result = value['result']
    dbx = Dropbox()
    filenames = ['ad_copy.csv', *COVERS.values()]
    receipts = value.get('artifacts') or {}
    if receipts and any(name not in receipts for name in filenames):
        return None
    files = [dbx.metadata_if_present(value['folder'] + '/' + name) for name in filenames]
    if not all(files):
        return None
    for name, meta in zip(filenames, files):
        receipt = receipts.get(name)
        if receipt and any(meta.get(field) != receipt[saved] for field, saved in
                           (('id','id'),('rev','rev'),('content_hash','hash'),('size','size'))):
            raise ValueError('A collected ad file changed after its receipt. Review the imported draft before posting.')
        if not (meta.get('id') and meta.get('rev') and meta.get('content_hash') and
                meta.get('path_display') == value['folder'] + '/' + name):
            raise ValueError('Dropbox returned an ad file outside this job’s exact delivery folder.')
    if len({meta['content_hash'] for meta in files[1:]}) != 3:
        raise ValueError('The three ad routes need distinct covers.')
    refs = ads_direct_post.references(posting.AD_TYPE, state={})
    from ads_companion_targeting import select
    targeting = select(refs, result, client=posting.MetaPostingClient(), saved=value.get('targeting'))
    set_id, audience = targeting['product_set_id'], targeting['audience']
    if value.get('targeting') != targeting:
        value['targeting'] = targeting
        write(PREFIX+value['upload'], value)
    copy = ads_page.parse_instant_experience_copy_csv(_download(dbx, files[0], 2 * 1024**2), result)
    creatives = []
    for (route, name), meta in zip(COVERS.items(), files[1:]):
        data = _download(dbx, meta, 20 * 1024**2)
        ads_image_workflow.inspect_instant_experience_original(data, original_name=name)
        record = ads_image_workflow.build_meta_posting_image_record(data, original_name=name)
        if not record['valid'] or record['source_format'] != 'JPEG':
            raise ValueError(f'{name} must be a valid full-resolution JPEG.')
        creatives.append(dict(copy[route][0], image=record))
    catalog_id = str(refs['catalog_resolution']['id'])
    if not posting._posting_form_ready(product_title=result['product_name'], product_url=result['product_url'],
            country=result['country'], sport=result['category'], creatives=creatives, catalog_id=catalog_id,
            product_set_id=set_id, dataset_id=refs['dataset_resolution']['id'],
            identities_ready=refs.get('page') and refs.get('instagram')):
        raise ValueError('The completed Dropbox files did not pass the Posting form checks.')
    return posting._build_posting_request(
        submission_id=_posting_id(value['upload']), product_id=result['product_id'],
        product_title=result['product_name'], product_handle=value['handle'], product_url=result['product_url'],
        country=canonical_posting_country(result['country']), sport=result['category'], catalog_id=catalog_id, product_set_id=set_id,
        audience=audience, creatives=creatives)


def _step(key, value, job, event, age):
    from ads_companion_controls import stopped
    from meta_posting_jobs import JOBS, TERMINAL, confirmed_ads
    from meta_posting_service import PostingBusyError

    stage = value['stage']
    if stage == 'waiting' and job['stage'] == 7:
        raise ValueError('Product publication or Edition Ops mapping needs attention.')
    if stage == 'preparing' and job['stage'] == 6:
        value.update(_prepare(value, job))
        write(key, value)
        stage, age = 'opening', 0
    chat_url = event.get('chat_url')
    if (isinstance(chat_url, str) and CHAT.fullmatch(chat_url)
            and event.get('state') in ('submitted', 'blocked') and not value.get('chat_url')):
        value['chat_url'] = chat_url
        write(key, value)
    if stage == 'opening' and event.get('state') == 'submitted':
        value.pop('prompt', None)
        stage, age = 'generating', 0
        value['stage'] = stage
        write(key, value)
    if stage in ('opening', 'generating') and not value.get('collect_only') and event.get('state') in ('failed', 'uncertain', 'blocked'):
        raise ValueError(str(event.get('reason') or 'Check the Meta Ads conversation for the blocked step.')[:600])
    if stage == 'opening':
        if age > 3600:
            raise ValueError('The desktop did not confirm the ChatGPT handoff.')
        return dict(id=value['upload'], project=PROJECT, receipt=_source_token(value['upload']),
                    prompt=value['prompt'], stage=stage)
    if stage == 'generating':
        if float((value.get('catalog_retry') or {}).get('next_at', 0)) > time.time():
            return {}
        transfer_detail = str(event.get('transfer_detail') or '')[:600]
        from ads_attachment_repair import advance as advance_repair
        repair_send = advance_repair(value, event)
        if value.get('attachment_repair'):
            write(key, value)
            if value['attachment_repair']['state'] in ('ready', 'sending'):
                from ads_companion_transfer import delivery
                return dict(delivery(value), repair_send=repair_send)
        if transfer_detail and transfer_detail != value.get('detail'):
            value['detail'] = transfer_detail
            write(key, value)
        from ads_companion_targeting import CatalogPending
        try:
            request = _post_request(value)
        except CatalogPending as error:
            now = time.time()
            retry = value.setdefault('catalog_retry', {'started_at': now, 'attempts': 0})
            if now - retry['started_at'] >= 86400:
                raise ValueError('Meta catalogue membership is still unverified after 24 hours. '
                                 'All four files are saved. Check the Shopify Meta sync and product-set rules, then Resume import.') from error
            retry['attempts'] += 1
            delay = min(900, 60 * 2 ** min(retry['attempts'] - 1, 4))
            retry.update(next_at=now + delay, reason=str(error))
            value.update(collect_only=True, detail=f'All ad files are saved. Waiting for Meta catalogue membership; checking again in {delay // 60} min. No regeneration needed.')
            write(key, value)
            return {}
        if request:
            if stopped(value['upload']): return {}
            try:
                value['posting_id'] = JOBS.submit(request)
            except PostingBusyError:
                return dict(id=value['upload'], stage=stage)
            value.pop('catalog_retry', None)
            value['detail'] = 'Files verified - creating ads paused for review'
            stage, age = 'posting', 0
            value['stage'] = stage
            write(key, value)
        elif age > 7200:
            raise ValueError('The three covers and ad copy did not arrive in Dropbox. Check the Meta Ads conversation.')
    if stage == 'posting':
        row = JOBS.snapshot(value['posting_id'])
        if row.get('status') == 'COMPLETE' and confirmed_ads(row) == (3, 3):
            value.update(stage='complete', detail='')
            write(key, value)
        elif row.get('status') in TERMINAL or (age > 1800 and not row.get('running_here') and not row.get('lease_active')):
            raise ValueError('Meta Posting needs review. Open the saved posting job to check its receipts.')
        return {}
    if stage == 'generating':
        from ads_companion_transfer import delivery
        return delivery(value)
    return dict(id=value['upload'], stage=stage)


def tick(token, event):
    from os_accounts import DEFAULT_STORE, can_access_page

    lease = str(uuid4())
    lease_key = PREFIX + 'lease'
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT 1 FROM product_upload_desktop WHERE singleton AND token_hash=%s FOR UPDATE',
                    (digest(token),))
        if not cur.fetchone():
            raise PermissionError('The paired desktop credential is required.')
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,'true',now())
            ON CONFLICT(key) DO UPDATE SET updated_at=now()""", (HEARTBEAT_KEY,))
        enabled = _enabled(cur)
        reported = str(event.get('id') or '')
        if re.fullmatch(r'[a-f0-9-]{36}',reported):
            cur.execute("SELECT 1 FROM app_settings WHERE key=%s AND value->>'action' IN ('cancel','delete')",('ads_job_control:'+reported,))
            if cur.fetchone(): return {'stop': {'id':reported}}
        cur.execute("""SELECT a.key, a.value,
            CASE WHEN a.value->>'source'='new_ads' THEN 6 ELSE j.stage END AS stage,
            j.intake_id, j.worker_actor, j.storefront,
            EXTRACT(EPOCH FROM now()-a.updated_at) AS age
            FROM app_settings a LEFT JOIN product_upload_staff_jobs j
                ON a.key=%s || j.id::text
            WHERE (j.id IS NOT NULL OR (a.key LIKE %s AND a.value->>'source'='new_ads'))
              AND NOT EXISTS (SELECT 1 FROM app_settings c WHERE c.key='ads_job_control:' || (a.value->>'upload')
                              AND c.value->>'action' IN ('cancel','delete'))
              AND COALESCE((a.value->'catalog_retry'->>'next_at')::double precision, 0) <= EXTRACT(EPOCH FROM now())
              AND (a.value->>'stage' IN ('preparing','opening','generating','posting')
               OR (a.value->>'stage'='waiting' AND
                   ((j.stage=6 OR a.value->>'source'='new_ads') AND %s)))
            ORDER BY (a.value->>'stage'='waiting') ASC, a.updated_at, a.key LIMIT 1""", (PREFIX, PREFIX + '%', enabled))
        job = cur.fetchone()
        if not job:
            return {}
        # A durable lease works with the Supabase transaction pool and survives Edge retries.
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
            WHERE app_settings.updated_at < now()-interval '10 minutes'
            RETURNING key""", (lease_key, json.dumps(lease)))
        if not cur.fetchone():
            return {'busy': True}
        # Read the selected checkpoint after claiming the lease, in case another
        # runner finished between selection and acquisition.
        cur.execute("""SELECT value, EXTRACT(EPOCH FROM now()-updated_at) AS age
                       FROM app_settings WHERE key=%s""", (job['key'],))
        current = cur.fetchone()
        key, value, age = job['key'], current['value'], float(current['age'])
        if value['stage'] == 'waiting' and job['stage'] == 6:
            value['stage'] = 'preparing'
            age = 0
            cur.execute('UPDATE app_settings SET value=%s::jsonb, updated_at=now() WHERE key=%s',
                        (json.dumps(value), key))
    try:
        from ads_companion_controls import stopped
        if stopped(value['upload']): return {}
        if value['stage'] in ('complete', 'failed'):
            return {}
        requester = DEFAULT_STORE.get_user(value['requester'])
        if not requester or not all(can_access_page(requester, page) for page in ('Ads', 'Posting', 'Files')):
            raise ValueError('The requesting account no longer has Ads, Posting and Files access.')
        delivered = event if event.get('id') == value['upload'] else {}
        return {'job': _step(key, value, job, delivered, age)}
    except ValueError as error:
        value.pop('prompt', None)
        value.update(stage='failed', detail=str(error)[:600])
        write(key, value)
        return {}
    except Exception:
        LOG.warning('Publish + ad could not advance; retaining the saved checkpoint', exc_info=True)
        if age > 7200:
            value.pop('prompt', None)
            value.update(stage='failed', detail='A dependency did not respond. Review the saved ad job.')
            write(key, value)
            return {}
        return {'busy': True}
    finally:
        with connect() as conn, conn.cursor() as cur:
            cur.execute('DELETE FROM app_settings WHERE key=%s AND value=%s::jsonb',
                        (lease_key, json.dumps(lease)))


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
            raise ValueError('Invalid ad job event.')
        return JSONResponse(await run_in_threadpool(tick, authorization[7:], event), headers=HEADERS)
    except Exception as error:
        return failure(error)
