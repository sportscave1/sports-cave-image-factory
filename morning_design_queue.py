"""Morning design jobs, using the existing paired Edge desktop credential."""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from product_upload_staff_queue import connect, digest

LABELS = ('Pending', 'Opening ChatGPT', 'Generating', 'Uploaded · checking review metadata',
          'Ready for review', 'Needs attention')
CHAT = re.compile(r'https://chatgpt\.com/g/g-p-6a1e449948e881919c1e345006d63654(?:-[a-z0-9-]+)?/c/[a-f0-9-]{36}')
LOG = logging.getLogger(__name__)


def _receipt(job):
    # Keep existing send journals valid; explicit retries get a fresh journal.
    retry = re.search(r'\nQueue retry receipt: ([a-f0-9-]{36})\n', job['prompt'])
    suffix = ':' + retry[1] if retry else ''
    return hashlib.sha256(('design:' + str(job['id']) + suffix).encode()).hexdigest()


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

def _job_prompt(key, title, recommendation, *, primary_market=""):
    from home_morning_brief_actions import _prompt
    return _prompt(title, recommendation, primary_market=primary_market) + (
        '\n\nAUTOMATIC DESIGN QUEUE RECEIPT\n'
        f'Include morning_design_job_id = "{key}" in the final .upload.json handoff. '
        'Keep this exact field even if the final title changes. Do not put it in the artwork. '
        'Save only to Design Studio Review; do not publish a product. '
        'Report Review delivery and artwork quality separately. Mark unresolved identity or other visual '
        'concerns needs_attention in the matching JSON even if delivery succeeds. After completing '
        'independent work, end your response with SC_DESIGN_BLOCKED: followed by the exact incomplete '
        'required workflow checkpoint, if one remains. Omit the marker for visual concerns alone.\n')


def _waiting_prompt(job):
    """Upgrade only unclaimed snapshots, keeping the saved brief and job ID."""
    prompt = job['prompt']
    if '\n\n**Start the authorised new-design job**\n\n' in prompt:
        from design_collector_titles import NEW_DESIGN_TITLE_GUIDANCE
        from design_new_composition import PURPOSEFUL_ABSTRACT
        from home_morning_brief_actions import REVIEW_SAVE_NAMING
        from design_motorsport import MOTORSPORT_JSON
        if all(rule in prompt for rule in (NEW_DESIGN_TITLE_GUIDANCE, PURPOSEFUL_ABSTRACT, REVIEW_SAVE_NAMING, MOTORSPORT_JSON)):
            return prompt
        _, _, body = prompt.partition('\n\n**Start the authorised new-design job**\n\n')
        _, _, body = body.partition('\n\n')  # Existing workflow introduction.
        brief, found, _ = body.partition('\n\n**1. Research the story, sources and master**')
        if found:
            upgraded = _job_prompt(str(job['id']), job['title'], brief)
            retry = re.search(r'\nQueue retry receipt: [a-f0-9-]{36}\n', prompt)
            return upgraded + (retry[0] if retry else '')
        return prompt  # Preserve unfamiliar snapshots rather than guessing at their brief.
    # Both legacy versions put the selected brief between these fixed sections.
    for boundary in (
        'Report PSD and JSON delivery separately from successful visual checks.',
        'Never label failed or unverified quality or production checks as passed.',
    ):
        _, found, body = prompt.partition(boundary + '\n\n')
        brief, end, _ = body.partition('\n\n**CHOOSE THE COLLECTOR TITLE AND DESIGN DIRECTION**')
        if found and end:
            return _job_prompt(str(job['id']), job['title'], brief)
    raise ValueError('The original design brief could not be recovered from the waiting prompt.')


def insert_suggestion(cur, day, section, item):
    key = identity(day, section, item)
    from home_brief_calendar import display_markets
    markets = display_markets(item)
    prompt = _job_prompt(key, item['title'], item['recommendation'],
                         primary_market=markets[0] if markets else '')
    cur.execute('''INSERT INTO morning_design_jobs(id,edition_date,section,title,prompt)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING''',
        (key, day, section, item['title'], prompt))



def settings(enabled=None):
    with connect() as conn, conn.cursor() as cur:
        if enabled is not None:
            cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
            cur.execute('''UPDATE morning_design_control SET enabled=%s,
                activated_at=CASE WHEN %s THEN COALESCE(activated_at,now()) ELSE activated_at END
                WHERE singleton''', (bool(enabled), bool(enabled)))
        cur.execute('SELECT * FROM morning_design_control WHERE singleton')
        return cur.fetchone()


def _live_artwork_key(path):
    from psd_directory import REVIEW_FOLDER, ROOT
    file = PurePosixPath(path)
    if file.parent.as_posix() not in (ROOT, REVIEW_FOLDER) or file.suffix.lower() != '.psd':
        return ''
    return (ROOT + '/' + file.name).lower().translate(str.maketrans('–—', '--'))


def _published_designs(cur, jobs):
    from psd_directory import ROOT
    saved = [job for job in jobs if job['file_id'] and job['file_path']]
    if not saved:
        return set()
    cur.execute('''SELECT m.dropbox_file_id, m.file_path,
            translate(lower(m.file_path), '–—', '--') AS artwork_key,
            s.status, s.online_store_url,
            h.operation_id IS NOT NULL AND NOT COALESCE(
                public.product_upload_mapping_complete(h.operation_id,h.product_gid,h.file_id), false
            ) AS pending_mapping,
            (SELECT max(u.created_at) FROM product_upload_staff_jobs u
             WHERE u.source_id=m.dropbox_file_id AND u.stage=6
               AND u.storefront=s.online_store_url) AS publish_upload_created
        FROM product_psd_mappings m
        LEFT JOIN shopify_products s ON s.shopify_product_id=m.shopify_product_gid
        LEFT JOIN product_upload_mapping_holds h ON h.product_gid=m.shopify_product_gid
        WHERE m.dropbox_file_id=ANY(%s)
           OR translate(lower(m.file_path), '–—', '--')=ANY(%s)''',
        (list({job['file_id'] for job in saved}),
         list({_live_artwork_key(job['file_path']) for job in saved} - {''})))
    by_file, by_title = {}, {}
    for mapping in cur.fetchall():
        by_file[mapping['dropbox_file_id']] = mapping
        by_title.setdefault(mapping['artwork_key'], []).append(mapping)

    published = set()
    for job in saved:
        mapping = by_file.get(job['file_id'])
        if mapping is None:
            # A separately saved PSD can fulfil the same design brief. Require
            # one exact artwork filename and a successful upload started after
            # that brief entered the queue.
            candidates = by_title.get(_live_artwork_key(job['file_path']), [])
            if len(candidates) != 1:
                continue
            mapping = candidates[0]
            receipt = mapping['publish_upload_created']
            if not receipt or receipt < job['created_at']:
                continue
        if (mapping['status'] == 'ACTIVE' and mapping['online_store_url'] and not mapping['pending_mapping']
                and PurePosixPath(mapping['file_path']).parent.as_posix() == ROOT):
            published.add(job['id'])
    return published


def _release_delivered(cur):
    """Legacy stage 3 already holds a verified PSD/receipt, not ongoing generation."""
    cur.execute("""UPDATE morning_design_jobs SET stage=5,
        message=concat_ws(' ', NULLIF(message,''),
            'PSD delivered to Design Studio Review. Upload metadata needs review; generation is complete and the queue continues.'),
        updated_at=now()
        WHERE stage=3 AND file_id<>'' AND file_rev<>'' AND file_path<>'' """)


def _deleted_designs(jobs, published):
    """Only confirmed absence permits redo; IDs survive Dropbox moves/renames."""
    from product_upload_services import Dropbox
    from psd_directory import ROOT
    candidates = [job for job in jobs if job['id'] not in published
                  and job['stage'] in (4, 5) and (job['file_id'] or job['file_path'])]
    if not candidates:
        return set()
    missing = set()
    try:
        provider = Dropbox()
        for job in candidates:
            paths = [job['file_id'], job['file_path']]
            if job['file_path']:
                paths.append(ROOT + '/' + PurePosixPath(job['file_path']).name)
            if all(provider.metadata_if_present(path) is None for path in dict.fromkeys(paths) if path):
                missing.add(job['id'])
    except Exception as error:
        LOG.warning('design_deletion_check_unavailable type=%s', type(error).__name__)
        return set()
    return missing


def _posted_designs(cur, jobs, published):
    """Retain successful publication receipts even if a product is later archived."""
    saved = [job for job in jobs if job['file_id']]
    if not saved:
        return published
    cur.execute('''SELECT source_id FROM product_upload_staff_jobs
        WHERE stage=6 AND source_id=ANY(%s)''', ([job['file_id'] for job in saved],))
    posted = {row['source_id'] for row in cur.fetchall()}
    return published | {job['id'] for job in saved if job['file_id'] in posted}


def list_jobs(day=None, *, display_only=False):
    from companion_read_connection import read_connection
    with (read_connection(connect) if display_only else connect()) as conn, conn.cursor() as cur:
        if not display_only:
            cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
            _release_delivered(cur)
        cur.execute('''SELECT * FROM morning_design_jobs WHERE (%s::date IS NULL OR edition_date=%s::date)
            ORDER BY (stage BETWEEN 0 AND 3) DESC,edition_date,created_at,id LIMIT 100''', (day, day))
        jobs = cur.fetchall()
        published = _published_designs(cur, jobs)
        posted = _posted_designs(cur, jobs, published)
    # Network checks must not hold the desktop claim lock.
    if display_only:
        from design_deletion_status import deleted as cached_deleted
        deleted = cached_deleted(jobs, posted)
    else:
        deleted = _deleted_designs(jobs, posted)
    return [dict(id=str(r['id']), title=r['title'],
                     label=('Completed · uploaded' if r['id'] in published
                            else 'Deleted · ready to redo' if r['id'] in deleted
                            else 'Uploaded · needs review' if r['stage'] == 5 and (r['file_id'] or r['file_path']) else LABELS[r['stage']]), stage=r['stage'],
                     chat_url=r['chat_url'], detail=r['message'], file_path=r['file_path'],
                     updated_at=r['updated_at'].isoformat(), created_at=r['created_at'].isoformat()) for r in jobs]


def verify_outputs(jobs):
    """Read actual Dropbox metadata; chat text alone cannot mark a design complete."""
    from product_upload_services import Dropbox
    from design_review_page import _folder_entries, final_psd
    from design_review_metadata import _read_sidecar, _handoff_details, handoff_paths
    from psd_directory import REVIEW_METADATA_FOLDER, REVIEW_FOLDER
    if not jobs:
        return {}
    wanted = {str(job['id']) for job in jobs}
    created = [job['created_at'] for job in jobs if isinstance(job.get('created_at'), datetime)]
    cutoff = min(created) - timedelta(minutes=5) if created else None
    provider, results, candidates = Dropbox(), {}, []
    for folder in (REVIEW_METADATA_FOLDER, REVIEW_FOLDER):
        try:
            candidates.extend(_folder_entries(provider, folder))
        except Exception as error:
            LOG.warning('design_receipt_folder_unavailable type=%s', type(error).__name__)
    seen = set()
    for metadata in candidates:
        if not metadata.get('name', '').endswith('.upload.json'):
            continue
        stamp = tuple(metadata.get(field) for field in ('id', 'rev', 'path_display', 'name'))
        if stamp in seen:
            continue
        seen.add(stamp)
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
            if any(value.get(field) != source.get(key) for field, key in (
                    ('dropbox_file_id', 'id'), ('dropbox_revision', 'rev'), ('dropbox_path', 'path_display'))):
                continue
            # Delivery completes generation. Publication metadata and artwork
            # quality remain review concerns, never a reason to occupy this slot.
            try:
                details = _handoff_details(value, source)
                stage = 4 if details['review_status'] == 'ready_for_review' else 5
                message = details.get('review_notes', '')
                if stage == 5:
                    message = ('PSD delivered to Design Studio Review. Generation is complete; '
                               'check artwork and upload metadata before publishing. ' + message).strip()
            except ValueError as error:
                stage = 5
                message = 'PSD delivered to Design Studio Review. Upload metadata needs review: ' + str(error)
            result = dict(stage=stage, source=source, message=message)
            if key in results and results[key]['source']['id'] != source['id']:
                result = dict(stage=5, source=source, message='Multiple final PSDs claim this job. Review them manually.')
            elif key in results and results[key]['stage'] == 5:
                result = results[key]
            results[key] = result
        except ValueError:
            continue
        except Exception as error:
            LOG.warning('design_receipt_unavailable type=%s', type(error).__name__)
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
        _release_delivered(cur)
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
        if enabled and cur.fetchone()['n'] == 0:
            cur.execute('''SELECT id,title,prompt FROM morning_design_jobs
                WHERE stage=0 ORDER BY edition_date,created_at,id LIMIT 1 FOR UPDATE''')
            waiting = cur.fetchone()
            if waiting:
                try:
                    prompt = _waiting_prompt(waiting)
                except ValueError as error:
                    cur.execute('''UPDATE morning_design_jobs SET stage=5,message=%s,updated_at=now()
                        WHERE id=%s AND stage=0''', (str(error), waiting['id']))
                else:
                    cur.execute('''UPDATE morning_design_jobs SET stage=1,prompt=%s,updated_at=now()
                        WHERE id=%s AND stage=0''', (prompt, waiting['id']))
        cur.execute('SELECT * FROM morning_design_jobs WHERE stage BETWEEN 1 AND 3 ORDER BY created_at,id')
        jobs = cur.fetchall()
    from home_morning_brief_actions import PROJECT_URL
    return dict(enabled=enabled, jobs=[dict(id=str(r['id']), stage=r['stage'], project=PROJECT_URL,
        prompt=r['prompt'], receipt=_receipt(r)) for r in jobs])


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
        # Serialize with desktop claims and competing homepage clicks.
        cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute('SELECT * FROM morning_design_jobs WHERE id=%s FOR UPDATE', (key,))
        job = cur.fetchone()
        if job:
            posted = _posted_designs(cur, [job], _published_designs(cur, [job]))
            deleted = job['id'] in _deleted_designs([job], posted)
            if job['id'] in posted or (not deleted and (job['stage'] != 5 or job['file_id'] or job['file_path'])):
                return False
            # Catch a late delivery before explicitly restarting failed work.
            if verify_outputs([job]):
                raise ValueError('This design has already been uploaded. Wait for its status to refresh.')
            prompt = _job_prompt(key, suggestion['item']['title'], suggestion['item']['recommendation'])
            prompt += f'\nQueue retry receipt: {uuid4()}\n'
            cur.execute('''UPDATE morning_design_jobs SET stage=0,prompt=%s,message='',
                chat_url='',file_id='',file_rev='',file_path='',updated_at=now() WHERE id=%s''', (prompt, key))
            return True
        insert_suggestion(cur, suggestion['date'], suggestion['section'], suggestion['item'])
        return True
