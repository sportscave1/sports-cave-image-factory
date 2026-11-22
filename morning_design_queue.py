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
CANCELLED = 'Cancelled by user.'

# Dropbox scans can outlive the desktop's HTTP deadline. One bounded background
# scan returns on a later poll; the existing prompt snapshot check rejects stale
# results after an explicit retry. Never queue an unbounded backlog of scans.
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
_verification_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='design-receipts')
_verification_lock = Lock()
_verification_future = None
_verification_prompts = {}


def poll_outputs(jobs):
    global _verification_future, _verification_prompts
    with _verification_lock:
        results = {}
        if _verification_future is not None and _verification_future.done():
            try:
                scanned = _verification_future.result()
                current = {str(job['id']): job['prompt'] for job in jobs}
                results = {key: result for key, result in scanned.items()
                           if current.get(str(key)) == _verification_prompts.get(str(key))}
            except Exception:
                LOG.warning('Design receipt scan failed; retrying on a later poll', exc_info=True)
            _verification_future = None
        if _verification_future is None and jobs:
            _verification_prompts = {str(job['id']): job['prompt'] for job in jobs}
            _verification_future = _verification_pool.submit(verify_outputs, jobs)
        return results


def _receipt(job):
    # Keep existing send journals valid; explicit retries get a fresh journal.
    retry = re.search(r'\nQueue retry receipt: ([a-f0-9-]{36})\n', job['prompt'])
    suffix = ':' + retry[1] if retry else ''
    return hashlib.sha256(('design:' + str(job['id']) + suffix).encode()).hexdigest()


def _output_key(job):
    # Manual repeats must not accept artwork delivered for a previous attempt.
    receipt = re.search(r'\nQueue output receipt: ([a-f0-9-]{36})\n', job.get('prompt', ''))
    return receipt[1] if receipt else str(job['id'])


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
        from home_sports_morning_brief import design_sections
        for section in design_sections(edition):
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
        'concerns needs_attention in the matching JSON even if delivery succeeds. Source resolution, '
        'photographic review and collector-art permission are handled in manual review after delivery; '
        'continue the complete design flow without a confirmation or approval pause. Report actual '
        'technical failures accurately and preserve completed work.\n')


def _waiting_refresh_prompt(job):
    """Refresh unclaimed jobs from the shared renderer without changing queue receipts."""
    from home_design_refresh import _refresh_prompt

    prompt = job['prompt']
    target = re.search(r'^Shopify product ID: (.+)$', prompt, re.M)
    if not target:
        raise ValueError('The queued refresh is missing its exact Shopify product ID.')
    _, found, tail = prompt.rpartition('\nInclude morning_design_job_id = "')
    if not found:
        raise ValueError('The queued refresh is missing its Review receipt.')
    tail = '\nInclude morning_design_job_id = "' + tail
    # Rebuild the brief as well as the stages: old snapshots explicitly allowed
    # a replacement title/story, which would contradict today's edition lock.
    page = re.search(r'^Product page(?: and current artwork reference)?: (.+)$', prompt, re.M)
    suggestion = re.search(r'^Research hypothesis from the Home recommendation: (.*?)\nDecision context:', prompt, re.M | re.S)
    evidence = re.search(r'^Decision context: (.+)$', prompt, re.M)
    if not page:
        raise ValueError('The queued refresh is missing its existing product reference.')
    rendered = _refresh_prompt(dict(
        title=job['title'], product_id=target[1].strip(),
        suggestion=suggestion[1].strip() if suggestion else 'Upgrade the imagery and collector finish for this existing edition.',
        evidence=evidence[1].strip() if evidence else 'Selected from Designs to Refresh.',
    ), page[1].strip())
    return 'SPORTS CAVE EXISTING DESIGN REFRESH\n' + rendered + tail


def _waiting_prompt(job):
    """Upgrade only unclaimed snapshots, keeping the saved brief and job ID."""
    prompt = job['prompt']
    if job.get('section') == 'edit':
        from design_execution_flow import CONTINUOUS_DESIGN_FLOW
        if CONTINUOUS_DESIGN_FLOW not in prompt:
            return CONTINUOUS_DESIGN_FLOW + prompt
        return prompt
    if prompt.startswith('SPORTS CAVE EXISTING DESIGN REFRESH\n'):
        return _waiting_refresh_prompt(job)
    if '\n\n**Start the authorised new-design job**\n\n' in prompt:
        from design_collector_titles import NEW_DESIGN_TITLE_GUIDANCE
        from design_new_composition import (PURPOSEFUL_ABSTRACT, COMPLEMENTARY_IMAGES, POSTER_IMAGE_SELECTION,
                                            COMPLETE_COMPOSITION, CREATIVE_REVIEW, REVIEW_RELATIONSHIPS)
        from design_collector_assets import NEW_BADGE_LAYOUT
        from design_collector_background import NEW_BACKGROUND_RESEARCH, NEW_COLLECTOR_BACKGROUND
        from home_morning_brief_actions import REVIEW_SAVE_NAMING
        from design_execution_flow import CONTINUOUS_DESIGN_FLOW
        from design_photographic_composition import STORY_FIRST_CROP, GENERATE_PHOTOGRAPHIC_UNIT, FINAL_PHOTOGRAPHIC_REVIEW
        from design_subject_authenticity import CREATE_DESIGN_AUTHENTICITY_CHECK
        from design_motorsport import (
            MOTORSPORT_JSON, MOTORSPORT_ARTWORK, MOTORSPORT_PLACEMENT,
            MOTORSPORT_INTEGRATION, MOTORSPORT_FINISH_CHECK,
        )
        if all(rule in prompt for rule in (CONTINUOUS_DESIGN_FLOW, NEW_DESIGN_TITLE_GUIDANCE, POSTER_IMAGE_SELECTION, PURPOSEFUL_ABSTRACT, COMPLEMENTARY_IMAGES, REVIEW_SAVE_NAMING,
                                          STORY_FIRST_CROP, GENERATE_PHOTOGRAPHIC_UNIT, FINAL_PHOTOGRAPHIC_REVIEW,
                                          COMPLETE_COMPOSITION, CREATIVE_REVIEW, REVIEW_RELATIONSHIPS, NEW_BADGE_LAYOUT,
                                          NEW_BACKGROUND_RESEARCH, NEW_COLLECTOR_BACKGROUND, CREATE_DESIGN_AUTHENTICITY_CHECK,
                                          MOTORSPORT_JSON, MOTORSPORT_ARTWORK, MOTORSPORT_PLACEMENT,
                                          MOTORSPORT_INTEGRATION, MOTORSPORT_FINISH_CHECK)):
            return prompt
        _, _, body = prompt.partition('\n\n**Start the authorised new-design job**\n\n')
        if '**CONTINUOUS DESIGN FLOW — NEW, EDIT AND REFRESH**' in body:
            _, _, body = body.partition('Display references/artwork and continue without pausing for approval.\n\n')
        else:
            _, _, body = body.partition('\n\n')  # Legacy workflow introduction.
        brief, found, _ = body.partition('\n\n**1. Research the story, sources and master**')
        if found:
            upgraded = _job_prompt(_output_key(job), job['title'], brief)
            retry = re.search(r'\nQueue retry receipt: [a-f0-9-]{36}\n', prompt)
            output = re.search(r'\nQueue output receipt: [a-f0-9-]{36}\n', prompt)
            return upgraded + (retry[0] if retry else '') + (output[0] if output else '')
        return prompt  # Preserve unfamiliar snapshots rather than guessing at their brief.
    # Both legacy versions put the selected brief between these fixed sections.
    for boundary in (
        'Report PSD and JSON delivery separately from successful visual checks.',
        'Never label failed or unverified quality or production checks as passed.',
    ):
        _, found, body = prompt.partition(boundary + '\n\n')
        brief, end, _ = body.partition('\n\n**CHOOSE THE COLLECTOR TITLE AND DESIGN DIRECTION**')
        if found and end:
            return _job_prompt(_output_key(job), job['title'], brief)
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


def _deleted_designs(jobs, published, *, exact_live_identity=False):
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
            if any(provider.metadata_if_present(path) is not None for path in dict.fromkeys(paths) if path):
                continue
            if job['file_path']:
                live = provider.metadata_if_present(ROOT + '/' + PurePosixPath(job['file_path']).name)
                # An older live product PSD is not the deleted refresh output.
                if live and (not exact_live_identity or not job['file_id'] or live.get('id') == job['file_id']):
                    continue
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
                            else 'Cancelled' if r['message'].startswith(CANCELLED)
                            else 'Pending · queue continues' if r['stage'] == 5 and not r['file_path']
                            else 'Uploaded · needs review' if r['stage'] == 5 and (r['file_id'] or r['file_path']) else LABELS[r['stage']]), stage=r['stage'],
                     cancelled=r['message'].startswith(CANCELLED),
                     can_cancel=(r['stage'] < 4 or r['stage'] == 5 and not r['file_path']) and not r['message'].startswith(CANCELLED),
                     can_defer=1 <= r['stage'] <= 3,
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
    wanted = {_output_key(job): str(job['id']) for job in jobs if job.get('section') != 'edit'}
    edits = {job['file_id']: job for job in jobs if job.get('section') == 'edit'}
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
            edit = edits.get(value.get('dropbox_file_id'))
            if edit:
                if value.get('dropbox_revision') == edit['file_rev']:
                    continue
                key = str(edit['id'])
            elif not isinstance(key, str) or key not in wanted:
                continue
            else:
                key = wanted[key]
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


def tick(token, events, capacity=1):
    from companion_poll_transaction import connection
    # Accept older two-slot clients so existing work can report and finish.
    # Admission is always one design, regardless of the advertised capacity.
    if type(capacity) is not int or capacity not in (1, 2):
        raise ValueError('Choose one or two design slots.')
    if not isinstance(events, list) or len(events) > 2 or any(not isinstance(e, dict) for e in events):
        raise ValueError('Send at most two existing design reports.')
    with connection(connect) as conn, conn.cursor() as cur:
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
        verified = poll_outputs(active)
    except Exception:
        verified = {}  # Connectivity failure is not proof of completion or failure.
    with connection(connect) as conn, conn.cursor() as cur:
        cur.execute('''SELECT actor_id FROM product_upload_desktop
            WHERE singleton AND token_hash=%s FOR UPDATE''', (digest(token),))
        if not cur.fetchone():
            raise PermissionError('The desktop pairing changed.')
        snapshots = {str(job['id']): job['prompt'] for job in active}
        for key, result in verified.items():
            cur.execute('SELECT prompt FROM morning_design_jobs WHERE id=%s', (key,))
            current = cur.fetchone()
            if not current or current['prompt'] != snapshots.get(str(key)):
                continue  # An explicit repeat superseded this provider lookup.
            source = result['source']
            cur.execute('''UPDATE morning_design_jobs SET stage=%s,file_id=%s,file_rev=%s,file_path=%s,
                message=%s,updated_at=CASE WHEN stage<>%s THEN now() ELSE updated_at END
                WHERE id=%s AND (stage BETWEEN 1 AND 3 OR (stage=5 AND (%s=4 OR file_path='')))''',
                (result['stage'], source['id'], source['rev'], source['path_display'], result['message'], result['stage'], key, result['stage']))
        for event in events:
            try:
                key = str(UUID(str(event.get('id'))))
            except ValueError:
                continue
            state = event.get('state')
            from design_queue_watchdog import observe
            observe(cur,key,event)
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
        from design_queue_watchdog import release_stalled
        release_stalled(cur)
        cur.execute('''UPDATE morning_design_jobs SET stage=5,
            message='Timed out. Inspect the saved ChatGPT conversation and Review folder; Queue continues; automatic resubmission is disabled.',
            updated_at=now() WHERE stage=1 AND updated_at < now()-interval '5 minutes' ''')
        discover(cur)
        cur.execute('SELECT enabled FROM morning_design_control WHERE singleton')
        enabled = cur.fetchone()['enabled']
        cur.execute('SELECT slot FROM morning_design_jobs WHERE stage BETWEEN 1 AND 3')
        occupied = {row['slot'] for row in cur.fetchall()}
        for slot in (1,) if enabled else ():
            if occupied:
                break
            if slot in occupied:
                continue
            cur.execute('''SELECT id,title,prompt,section FROM morning_design_jobs
                WHERE stage=0 ORDER BY edition_date,created_at,id LIMIT 1 FOR UPDATE''')
            waiting = cur.fetchone()
            if waiting:
                try:
                    prompt = _waiting_prompt(waiting)
                except ValueError as error:
                    cur.execute('''UPDATE morning_design_jobs SET stage=5,message=%s,updated_at=now()
                        WHERE id=%s AND stage=0''', (str(error), waiting['id']))
                else:
                    cur.execute('''UPDATE morning_design_jobs SET stage=1,slot=%s,prompt=%s,updated_at=now()
                        WHERE id=%s AND stage=0''', (slot, prompt, waiting['id']))
                    occupied.add(slot)
        cur.execute('SELECT * FROM morning_design_jobs WHERE stage BETWEEN 1 AND 3 ORDER BY slot')
        jobs = cur.fetchall()
    from home_morning_brief_actions import PROJECT_URL
    return dict(enabled=enabled, jobs=[dict(id=str(r['id']), stage=r['stage'], kind=r['section'], project=PROJECT_URL,
        prompt=r['prompt'], receipt=_receipt(r)) for r in jobs], capacity=1)


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
        result = await run_in_threadpool(tick, authorization[7:], body.get('events', []), body.get('capacity', 1))
        return JSONResponse(result, headers=HEADERS)
    except Exception as error:
        return failure(error)


def control(key, user, expected, action):
    from product_upload_staff_queue import can_control_queues
    if not can_control_queues(user):
        raise PermissionError('An administrator must control design jobs.')
    key = UUID(str(key))
    if action not in ('cancel', 'defer') or not isinstance(expected, str) or not expected:
        raise ValueError('Refresh the design status before changing this job.')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT actor_id FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute('SELECT * FROM morning_design_jobs WHERE id=%s FOR UPDATE', (key,))
        job = cur.fetchone()
        allowed = job and (job['stage'] in (1, 2, 3) if action == 'defer' else
                          (job['stage'] < 4 or job['stage'] == 5 and not job['file_path'])
                          and not job['message'].startswith(CANCELLED))
        if not allowed or job['updated_at'] != datetime.fromisoformat(expected):
            raise ValueError('This design changed. Refresh its status and try again.')
        message = (CANCELLED if action == 'cancel' else 'Moved to pending by user.') + (
            ' Queue continues. Saved chat and files retained; no automatic resubmission. Late verified delivery will still be checked.')
        cur.execute('UPDATE morning_design_jobs SET stage=5,message=%s,updated_at=now() WHERE id=%s', (message, key))
    return dict(id=str(key), stage=5)


async def control_route(request):
    from product_upload_api import HEADERS, actor, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user = await actor(request, write=True)
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Choose a design job.')
        job = await run_in_threadpool(control, body.get('id'), user, body.get('updated_at'), body.get('action'))
        return JSONResponse({'job': job}, headers=HEADERS)
    except Exception as error:
        return failure(error)


ROUTES = (('/api/morning-designs/tick', tick_route, ('POST',)),
          ('/api/morning-designs/control', control_route, ('POST',)))


def current_suggestions():
    from home_sports_morning_brief import SETTING_KEY, design_sections
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (SETTING_KEY,))
        row = cur.fetchone()
    edition = row['value'] if row else {}
    return [dict(id=identity(edition['date'], section, item), date=edition['date'], section=section, item=item)
            for section in design_sections(edition) for item in edition.get(section, [])]


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
            if job['stage'] in (0, 1, 2):
                return False  # Already queued/running; do not interrupt an active attempt.
            receipt = str(uuid4())
            from home_brief_calendar import display_markets
            markets = display_markets(suggestion['item'])
            prompt = _job_prompt(receipt, suggestion['item']['title'], suggestion['item']['recommendation'],
                                 primary_market=markets[0] if markets else '')
            prompt += f'\nQueue retry receipt: {receipt}\nQueue output receipt: {receipt}\n'
            cur.execute('''UPDATE morning_design_jobs SET stage=0,prompt=%s,message='',
                chat_url='',file_id='',file_rev='',file_path='',updated_at=now() WHERE id=%s''', (prompt, key))
            return True
        insert_suggestion(cur, suggestion['date'], suggestion['section'], suggestion['item'])
        return True
