"""Morning design jobs, using the existing paired Edge desktop credential."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5, NAMESPACE_URL

from product_upload_staff_queue import connect, digest

LABELS = ('Pending', 'Opening ChatGPT', 'Generating', 'Uploaded · checking review metadata',
          'Ready for review', 'Needs attention')
CHAT = re.compile(r'https://chatgpt\.com/g/g-p-6a1e449948e881919c1e345006d63654(?:-[a-z0-9-]+)?/c/[a-f0-9-]{36}')


def identity(day, section, item):
    # Editorial corrections and reordering do not repeat a design already claimed.
    title = ' '.join(item['title'].split()).casefold()
    return str(uuid5(NAMESPACE_URL, f'sports-cave-morning-design:{day}:{section}:{title}'))


def discover(cur):
    from home_brief_calendar import HISTORY_PREFIX
    cur.execute('''SELECT value FROM app_settings, morning_design_control c
        WHERE c.singleton AND c.enabled AND starts_with(key,%s)
        AND value->>'date' >= c.start_date::text AND updated_at >= c.activated_at ORDER BY key''', (HISTORY_PREFIX,))
    editions = cur.fetchall()
    cur.execute('SELECT id FROM morning_design_jobs')
    existing = {str(row['id']) for row in cur.fetchall()}
    for row in editions:
        edition = row['value']
        for section in ('recommendations', 'legends'):
            for item in edition.get(section, []):
                key = identity(edition['date'], section, item)
                if key in existing:
                    continue
                insert_suggestion(cur, edition['date'], section, item)

def insert_suggestion(cur, day, section, item):
    from home_morning_brief_actions import _prompt
    key = identity(day, section, item)
    prompt = _prompt(item['title'], item['recommendation']) + (
        '\n\nAUTOMATIC DESIGN QUEUE RECEIPT\n'
        f'Include morning_design_job_id = "{key}" in the final .upload.json handoff. '
        'Keep this exact field even if the final title changes. Do not put it in the artwork. '
        'Save only to Design Studio Review; do not publish a product. '
        'If the workflow cannot finish, end your response with SC_DESIGN_BLOCKED: followed by the exact reason.\n')
    cur.execute('''INSERT INTO morning_design_jobs(id,edition_date,section,title,prompt)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING''',
        (key, day, section, item['title'], prompt))



def settings(enabled=None):
    with connect() as conn, conn.cursor() as cur:
        if enabled is not None:
            cur.execute('''UPDATE morning_design_control SET enabled=%s,
                activated_at=CASE WHEN %s THEN COALESCE(activated_at,now()) ELSE activated_at END
                WHERE singleton''', (bool(enabled), bool(enabled)))
        cur.execute('SELECT * FROM morning_design_control WHERE singleton')
        return cur.fetchone()


def list_jobs(day=None):
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT * FROM morning_design_jobs WHERE (%s::date IS NULL OR edition_date=%s::date)
            ORDER BY edition_date DESC,created_at,id LIMIT 100''', (day, day))
        return [dict(id=str(r['id']), title=r['title'],
                     label='Uploaded · needs review' if r['stage'] == 5 and r['file_path'] else LABELS[r['stage']], stage=r['stage'],
                     chat_url=r['chat_url'], detail=r['message'], file_path=r['file_path']) for r in cur.fetchall()]


def verify_outputs(jobs):
    """Read actual Dropbox metadata; chat text alone cannot mark a design complete."""
    from product_upload_services import Dropbox
    from design_review_page import _folder_entries, final_psd
    from design_review_metadata import _read_sidecar, _handoff_details, handoff_paths
    from psd_directory import REVIEW_METADATA_FOLDER
    if not jobs:
        return {}
    wanted = {str(job['id']) for job in jobs}
    created = [job['created_at'] for job in jobs if isinstance(job.get('created_at'), datetime)]
    cutoff = min(created) - timedelta(minutes=5) if created else None
    provider, results = Dropbox(), {}
    for metadata in _folder_entries(provider, REVIEW_METADATA_FOLDER):
        if not metadata.get('name', '').endswith('.upload.json'):
            continue
        # Old sidecars cannot contain a newly allocated job receipt. Listing is
        # paginated, but only recent candidates need file-content downloads.
        modified = metadata.get('server_modified')
        if cutoff and isinstance(modified, str):
            try:
                timestamp = datetime.fromisoformat(modified.replace('Z', '+00:00'))
                if timestamp.replace(tzinfo=timestamp.tzinfo or timezone.utc) < cutoff:
                    continue
            except ValueError:
                pass
        try:
            value, actual = _read_sidecar(provider, metadata)
            key = value.get('morning_design_job_id')
            if not isinstance(key, str) or key not in wanted:
                continue
            source = provider.metadata_if_present(value.get('dropbox_file_id', ''))
            if not source or not final_psd(source) or source.get('size', 0) <= 0:
                continue
            if actual.get('path_display') not in handoff_paths(source['path_display']):
                continue
            details = _handoff_details(value, source)
            stage = 4 if details['review_status'] == 'ready_for_review' else 3
            # A completed handoff can honestly flag artwork quality for review.
            # It must release the generation slot without claiming visual approval.
            if (value.get('review_status') == 'needs_attention' and details['design_name']
                    and details['intended_collections'] and details['sport']):
                stage = 5
            result = dict(stage=stage, source=source, message=details.get('review_notes', ''))
            if key in results and (results[key]['stage'] == 5 or results[key]['source']['id'] != source['id']):
                result = dict(stage=5, source=source, message='Multiple final PSDs claim this job. Review them manually.')
            results[key] = result
        except ValueError:
            continue
    return results


def tick(token, events):
    if not isinstance(events, list) or len(events) > 1 or any(not isinstance(e, dict) for e in events):
        raise ValueError('Send at most one design job report.')
    with connect() as conn, conn.cursor() as cur:
        # Same singleton lock as Product Uploads serializes all desktop claims.
        cur.execute('''UPDATE product_upload_desktop SET seen_at=now()
            WHERE singleton AND token_hash=%s RETURNING actor_id''', (digest(token),))
        if not cur.fetchone():
            raise PermissionError('Pair the existing Upload Companion first.')
        cur.execute("SELECT * FROM morning_design_jobs WHERE stage BETWEEN 1 AND 3 OR (stage=5 AND updated_at>now()-interval '1 day')")
        active = cur.fetchall()
    # Provider calls are deliberately outside the claim transaction.
    try:
        verified = verify_outputs(active)
    except Exception:
        verified = {}  # Connectivity failure is not proof of completion or failure.
    with connect() as conn, conn.cursor() as cur:
        cur.execute('''SELECT actor_id FROM product_upload_desktop
            WHERE singleton AND token_hash=%s FOR UPDATE''', (digest(token),))
        if not cur.fetchone():
            raise PermissionError('The desktop pairing changed.')
        for key, result in verified.items():
            source = result['source']
            cur.execute('''UPDATE morning_design_jobs SET stage=%s,file_id=%s,file_rev=%s,file_path=%s,
                message=%s,updated_at=CASE WHEN stage<>%s THEN now() ELSE updated_at END
                WHERE id=%s AND (stage BETWEEN 1 AND 3 OR (stage=5 AND (%s=4 OR file_id='')))''',
                (result['stage'], source['id'], source['rev'], source['path_display'], result['message'], result['stage'], key, result['stage']))
        for event in events:
            try:
                key = str(UUID(str(event.get('id'))))
            except ValueError:
                continue
            state = event.get('state')
            stage = 2 if state == 'submitted' else 5 if state in ('failed', 'uncertain', 'blocked') else None
            if stage is None:
                continue
            chat = event.get('chat_url', '')
            chat = chat if isinstance(chat, str) and CHAT.fullmatch(chat) else ''
            if chat:
                cur.execute('UPDATE morning_design_jobs SET chat_url=%s WHERE id=%s AND stage BETWEEN 1 AND 5', (chat, key))
            cur.execute('''UPDATE morning_design_jobs SET stage=%s,message=%s,
                chat_url=CASE WHEN %s<>'' THEN %s ELSE chat_url END,updated_at=now()
                WHERE id=%s AND (stage=1 OR (stage BETWEEN 2 AND 3 AND %s=5))''',
                (stage, str(event.get('reason') or '')[:1600], chat, chat, key, stage))
        cur.execute('''UPDATE morning_design_jobs SET stage=5,
            message='Timed out. Inspect the saved ChatGPT conversation and Review folder; Queue continues; automatic resubmission is disabled.',
            updated_at=now() WHERE stage BETWEEN 1 AND 3 AND updated_at < now()-interval '3 hours' ''')
        discover(cur)
        cur.execute('SELECT enabled FROM morning_design_control WHERE singleton')
        enabled = cur.fetchone()['enabled']
        cur.execute('SELECT count(*) AS n FROM morning_design_jobs WHERE stage BETWEEN 1 AND 3')
        slots = 1 - cur.fetchone()['n']
        if enabled and slots > 0:
            cur.execute('''UPDATE morning_design_jobs SET stage=1,updated_at=now() WHERE id IN
                (SELECT id FROM morning_design_jobs WHERE stage=0 ORDER BY edition_date,created_at,id LIMIT %s)''', (slots,))
        cur.execute('SELECT * FROM morning_design_jobs WHERE stage BETWEEN 1 AND 3 ORDER BY created_at,id')
        jobs = cur.fetchall()
    from home_morning_brief_actions import PROJECT_URL
    return dict(enabled=enabled, jobs=[dict(id=str(r['id']), stage=r['stage'], project=PROJECT_URL,
        prompt=r['prompt'], receipt=hashlib.sha256(('design:'+str(r['id'])).encode()).hexdigest()) for r in jobs])


async def tick_route(request):
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        authorization = request.headers.get('authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', authorization):
            raise PermissionError('Desktop credential required.')
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Invalid design report.')
        result = await run_in_threadpool(tick, authorization[7:], body.get('events', []))
        return JSONResponse(result, headers=HEADERS)
    except Exception as error:
        return failure(error)


ROUTES = (('/api/morning-designs/tick', tick_route, ('POST',)),)


def current_suggestions():
    from home_sports_morning_brief import SETTING_KEY
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (SETTING_KEY,))
        row = cur.fetchone()
    edition = row['value'] if row else {}
    return [dict(id=identity(edition['date'], section, item), date=edition['date'], section=section, item=item)
            for section in ('recommendations', 'legends') for item in edition.get(section, [])]


def enqueue_selected(key):
    suggestion = next((entry for entry in current_suggestions() if entry['id'] == key), None)
    if not suggestion:
        raise ValueError('The suggestion changed. Refresh the current Morning Brief.')
    with connect() as conn, conn.cursor() as cur:
        insert_suggestion(cur, suggestion['date'], suggestion['section'], suggestion['item'])
