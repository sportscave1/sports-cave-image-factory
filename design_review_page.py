"""Design Studio gallery for the exact PSDs in the Dropbox review folder."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from html import escape
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode
import logging

import streamlit as st

from design_review_metadata import (
    handoff_paths, is_refresh_staging, is_working_file, legacy_metadata, read_gallery_handoff, read_handoff,
    resolve_review_sport, review_key, save_review_sport,
)
from product_upload_dropbox import REVIEW, approved, select, within
from product_upload_intake import Intakes, action_mode, stored_mode
from psd_directory import REVIEW_METADATA_FOLDER

_HANDOFF_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='review-handoff')


def final_psd(entry):
    return bool(approved(entry) and within(entry['path_display'], REVIEW)
                and entry.get('rev')
                and not is_working_file(entry['name']))


def _folder_entries(provider, path):
    cursor, seen = '', set()
    while True:
        page = provider.api.list_folder_page(provider.token, path, cursor=cursor, limit=500)
        yield from page['entries']
        if not page.get('has_more'):
            return
        cursor = page.get('cursor')
        if not cursor or cursor in seen:
            raise ValueError('Review folder pagination could not be completed.')
        seen.add(cursor)


def status(row, job, details):
    data = (row or {}).get('data') or {}
    if data.get('product_gid'):
        return 'Published' if data.get('shopify_completion') != 'Draft confirmed' else 'Needs attention'
    decision = (data.get('design_review') or {}).get('decision')
    if decision == 'rejected':
        return 'Rejected'
    if decision == 'changes' or (job or {}).get('state') == 'Failed':
        return 'Needs attention'
    if (job or {}).get('state') in ('Queued', 'Running'):
        return 'Generating mockups'
    if data.get('mockups_exported'):
        return 'Ready for Shopify handoff'
    if (job or {}).get('state') == 'Ready':
        return 'Mockups ready'
    if details.get('review_status') == 'ready_for_review':
        return 'Ready to publish'
    return 'Needs attention' if details.get('review_status') == 'needs_attention' else 'In review'


def _review(provider, user, entry, command, *, selected_sport=None):
    from product_upload_api import connect
    from product_upload_jobs import JOBS
    actor = user['id']
    key = review_key(entry)
    current = provider.metadata_if_present(entry['id'])
    if not current or not final_psd(current) or current.get('rev') != entry['rev']:
        raise ValueError('This PSD changed. Reload and review its current revision.')
    store = Intakes(connect)
    existing = store.read_review(key, actor, current)
    if existing:
        key = str(existing['id'])
    if existing and existing['data'].get('product_gid'):
        return key
    job = JOBS.snapshot(key, actor, 'generate')
    if command != 'approved' and job and job['state'] in ('Queued', 'Running'):
        raise ValueError('The approved job is already generating mockups.')
    if command == 'approved':
        original_details = read_handoff(provider, current, allow_stale_sport=True) or legacy_metadata(current)
        saved_data = (existing or {}).get('data') or {}
        details = resolve_review_sport(original_details, saved_data.get('review_sport') or selected_sport)
        if not details.get('sport'):
            raise ValueError('The sport could not be resolved from this PSD or its metadata.')
        if details != original_details or details.get('sport_normalization_pending'):
            details = save_review_sport(provider, current, details['sport']) or details
        if details.get('refresh_target_pending'):
            raise ValueError('Verify the Shopify refresh target for this PSD revision in Design Studio.')
        if details.get('shopify_product_id'):
            from shopify_sync import fetch_product_by_shopify_id
            target = fetch_product_by_shopify_id(details['shopify_product_id'])
            if target.get('shopify_product_id') != details['shopify_product_id'] or target.get('status') not in ('ACTIVE', 'DRAFT'):
                raise ValueError('The exact Shopify refresh target is unavailable.')
    if not existing:
        reviewed = (current, original_details) if command == 'approved' else None
        existing = select(connect, provider, key, actor, 'SMART' if command == 'approved' else 'LIVE',
                          entry['id'], entry['rev'], reviewed=reviewed)
    key = str(existing['id'])
    if command == 'approved' and action_mode(existing) != 'SMART':
        store.change_mode(key, actor, 'SMART', metadata=details)
    with store.locked(key, actor) as (row, _):
        if any(row['data']['source'].get(field) != current.get(field)
               for field in ('id', 'rev', 'path_display', 'content_hash', 'size')):
            raise ValueError('This intake belongs to another artwork revision.')
        if row['data'].get('product_gid'):
            return key
        if command == 'approved':
            data = row['data']
            prior_decision = (data.get('design_review') or {}).get('decision')
            if prior_decision == 'preparing' and not data.get('copied'):
                data['metadata'] = details
                row['mode'] = stored_mode('SMART', details)
            elif details != original_details and data.get('metadata') == original_details:
                data['metadata'] = details
            if data.get('metadata') != details:
                raise ValueError('The upload metadata changed. Review the exact PSD again.')
            if details != original_details:
                data['review_sport'] = details['sport']
        row['data']['design_review'] = dict(decision=command, at=datetime.now(timezone.utc).isoformat())
    return key


def _artwork(source, title, *, eager=False):
    url = escape('/api/design-review/thumbnail?' + urlencode(dict(id=source['id'], rev=source['rev'])), quote=True)
    description = escape(f'Open artwork preview for {title} in a new tab', quote=True)
    loading = 'eager' if eager else 'lazy'
    st.html(f'<a class="sc-review-artwork" href="{url}" target="_blank" rel="noopener" aria-label="{description}">'
            f'<img src="{url}" alt="" width="1024" height="724" loading="{loading}" decoding="async"></a>')


def _edit_link(source, title):
    from home_morning_brief_actions import PROJECT_URL

    endpoint = '/api/design-review/edit-prompt?' + urlencode(dict(id=source['id'], rev=source['rev']))
    st.html(f'<a class="sc-review-edit" href="{PROJECT_URL}" target="_blank" rel="noopener noreferrer" '
            f'data-design-review-prompt="{escape(endpoint, quote=True)}" '
            f'aria-label="{escape(f"Edit {title}", quote=True)}" '
            f'title="{escape(f"Edit {title} in Sports Cave Designs", quote=True)}">'
            'Edit</a>')


def _staged_replacement(user, source, key):
    from product_upload_api import Dropbox

    with st.expander('Apply staged replacement'):
        st.caption('Use this when ChatGPT can stage the edit in Dropbox but cannot apply a revision-checked update.')
        stem = str(PurePosixPath(source['path_display']).with_suffix('')) + ' - EDIT-' + source['rev']
        trial = st.text_input('Trial PSD path (optional, legacy edits only)', value='', key=key+'-trial')
        staged = st.text_input('Staged final PSD path', value=stem + ' - STAGING.psd', key=key+'-staged')
        title = st.text_input('New design title (optional)', key=key+'-new-title', max_chars=400)
        review_notes = st.text_area('Unresolved review notes (optional)', key=key+'-review-notes',
                                    help='Record missing source photographs or inherited limitations. These keep the replacement marked Needs attention, without approving publication.')
        number_checked = st.checkbox('I verified the live edition number updates in place and restored its value in the staged PSD.',
                                     key=key+'-number-checked')
        if st.button('Apply staged replacement', type='primary', disabled=not number_checked, key=key+'-replace'):
            from design_review_replace import apply
            from design_review_title import unclaimed_artwork
            try:
                with st.spinner('Checking both saved files and replacing the exact revision'):
                    final, _, warnings = apply(Dropbox(), source, trial, staged, title=title, review_notes=review_notes, title_guard=unclaimed_artwork)
            except ValueError as error:
                st.error(str(error))
            except Exception:
                logging.getLogger(__name__).exception('Design Studio replacement failed')
                st.error('The replacement could not be confirmed. Check the original, backup and staged files before retrying.')
            else:
                _folder.clear(str(user['id']))
                st.session_state['_review_replace_result'] = (final['path_display'], warnings)
                st.rerun()


def _keep_original(user, source, key):
    from product_upload_api import Dropbox

    with st.expander('Keep original and finish edit'):
        paths = st.text_area('Dropbox draft paths from this edit', key=key+'-closeout-paths',
                             help='Enter one draft per line. Paste the path or the recorded path | file ID | revision.')
        if st.button('Keep original and finish edit', key=key+'-keep-original', disabled=not paths.strip()):
            from design_review_replace import keep_original
            try:
                with st.spinner('Verifying the original and removing the selected drafts'):
                    warnings = keep_original(Dropbox(), source, paths.splitlines())
            except ValueError as error:
                st.error(str(error))
            except Exception:
                logging.getLogger(__name__).exception('Design Studio edit closeout failed')
                st.error('The edit could not be closed. Refresh Design Studio to check the original and drafts.')
            else:
                _folder.clear(str(user['id']))
                st.session_state['_review_keep_result'] = (source['name'], warnings)
                st.rerun()


def _selection_changed():
    # Checkbox changes reuse this session's displayed data, without Dropbox/SQL I/O.
    st.session_state['_review_selection_only'] = True


def _selection_key(source):
    return 'design-review-select-' + review_key(source)


@st.dialog('Delete Review designs?', dismissible=False)
def _confirm_delete(user, selected):
    from design_review_delete import delete_design
    from files_upload_api import invalidate_directory_cache, invalidate_thumbnail_cache
    from os_accounts import can_delete_files
    from product_upload_api import Dropbox

    st.write('Stop pending uploads and move the selected PSDs and their matching upload JSON files to Dropbox Deleted Files.')
    st.text('\n'.join(title for _, title in selected))
    cancel, confirm = st.columns(2)
    if cancel.button('Cancel', key='design-review-delete-cancel'):
        st.session_state.pop('_review_delete_selection', None)
        st.rerun()
    if not confirm.button('Delete from Dropbox', type='primary', key='design-review-delete-confirm'):
        return
    if not can_delete_files(user):
        st.error('Your account does not have permission to delete Dropbox files.')
        return
    deleted, warnings = [], []
    try:
        provider = Dropbox()
    except Exception:
        logging.getLogger(__name__).exception('Dropbox is unavailable for Review deletion')
        st.error('Dropbox is unavailable. Try again or cancel.')
        return
    with st.spinner('Removing selected designs from Dropbox'):
        for source, title in selected:
            try:
                warnings.extend(delete_design(provider, source, user=user))
            except ValueError as error:
                warnings.append(f'{title}: {error}')
            except Exception:
                logging.getLogger(__name__).exception('Could not delete Review PSD %s', source['id'])
                warnings.append(f'{title}: Dropbox did not confirm removal.')
            else:
                deleted.append(source['path_display'])
                st.session_state.pop(_selection_key(source), None)
    _folder.clear()
    invalidate_directory_cache(REVIEW, REVIEW_METADATA_FOLDER)
    invalidate_thumbnail_cache(*deleted)
    st.session_state['_review_delete_result'] = (len(deleted), warnings)
    st.session_state.pop('_review_delete_selection', None)
    st.rerun()


@lru_cache(maxsize=512)
def _handoff(actor_id, file_id, revision, path, sidecars):
    from product_upload_api import Dropbox
    candidates = (dict(id=id_, rev=rev, size=size, **{'.tag': 'file'}) for id_, rev, size in sidecars)
    return read_gallery_handoff(Dropbox(), dict(id=file_id, rev=revision, path_display=path), candidates)


def _details(actor, source, sidecars):
    if not sidecars:
        return legacy_metadata(source), ''
    try:
        versions = tuple((sidecar.get('id'), sidecar.get('rev'), sidecar.get('size')) for sidecar in sidecars)
        return _handoff(actor, source['id'], source['rev'], source['path_display'],
                        versions) or legacy_metadata(source), ''
    except ValueError as exc:
        return dict(legacy_metadata(source), review_status='needs_attention'), str(exc)
    except Exception:
        return dict(legacy_metadata(source), review_status='needs_attention'), 'Upload metadata could not be read for this PSD.'


def _synced_design(provider, actor, source, sidecars, editing, has_edit_files):
    details, reason = _details(actor, source, sidecars)
    pending = details.get('title_sync_pending')
    if pending:
        details = {key: value for key, value in details.items() if key != 'title_sync_pending'}
    title = details.get('design_name')
    if (sidecars and not reason and not editing and not has_edit_files
            and details.get('sport_normalization_pending') and not pending
            and not is_refresh_staging(source['name']) and details.get('cleanup_status') != 'pending'):
        try:
            details = save_review_sport(provider, source, details['sport'], candidates=sidecars) or details
            sidecars = tuple(provider.metadata_if_present(item['id']) for item in sidecars)
        except Exception:
            logging.getLogger(__name__).exception('Review sport JSON save failed')
            reason = 'The sport could not be saved to the matching JSON. Refresh Design Studio to retry.'
    if (sidecars and title and not reason and not has_edit_files
            and not is_refresh_staging(source['name']) and details.get('cleanup_status') != 'pending'):
        from design_review_title import resume_review_title, sync_review_title, title_destination, unclaimed_artwork
        try:
            if pending:
                source, reason = resume_review_title(provider, source, sidecars, guard=unclaimed_artwork)
                details = read_handoff(provider, source) or details
            elif title_destination(source, title) != source['path_display']:
                source, reason = sync_review_title(provider, source, candidates=sidecars, guard=unclaimed_artwork)
        except ValueError as error:
            reason = str(error)
        except Exception:
            logging.getLogger(__name__).exception('Design Review title sync failed')
            reason = 'Dropbox could not synchronise the design title. Refresh Design Studio to retry.'
    return source, details, reason, editing


@st.fragment
def _card(app, user, source, details, reason, key, row, *, editing=False, eager=False,
          show_replacement=False, selectable=False):
    from product_upload_api import Dropbox
    from product_upload_jobs import JOBS
    card_key = key
    if row:
        key = str(row['id'])
    job = JOBS.snapshot(key, user['id'], 'generate') if row else None
    title = details.get('design_name') or PurePosixPath(source['name']).stem
    staged = is_refresh_staging(source['name'])
    cleanup_pending = staged or details.get('cleanup_status') == 'pending'
    current = status(row, job, details)
    if editing and current in ('Ready to publish', 'In review'):
        current = 'Editing'
    with st.container(key=f'design-review-card-{card_key}'):
        _artwork(source, title, eager=eager)
        published = bool(row and row['data'].get('product_gid'))
        resumable = current in ('Generating mockups', 'Mockups ready', 'Ready for Shopify handoff')
        decision = ((row or {}).get('data', {}).get('design_review') or {}).get('decision')
        chosen_sport = (row or {}).get('data', {}).get('review_sport')
        needs_sport = not (published or editing or staged or resumable or chosen_sport or details.get('sport'))
        if selectable and not staged:
            check, name, edit_button, delete_button, publish, publish_ad = st.columns((.5, 4, .6, .6, 1.5, 1.5), vertical_alignment='center', gap='small')
            check.checkbox(f'Select {title}', key=_selection_key(source), label_visibility='collapsed',
                           on_change=_selection_changed)
            if st.session_state.get('_review_selection_only'):
                st.rerun()
        else:
            name, edit_button, delete_button, publish, publish_ad = st.columns((4, .6, .6, 1.5, 1.5), vertical_alignment='center', gap='small')
        note = (job or {}).get('error') or reason or details.get('review_notes') or current
        label = 'Needs attention' if reason and current in ('In review', 'Ready to publish') else current
        if cleanup_pending:
            if label == 'Ready to publish' and staged:
                label = 'Ready for review'
            label = f'{label} · Cleanup pending'
        name.html(f'<h3 class="sc-review-title" title="{escape(title, quote=True)}">{escape(title)}</h3>'
                  + (f'<div class="sc-review-status" title="{escape(note, quote=True)}">{escape(label)}</div>'
                     if cleanup_pending or reason or current not in ('In review', 'Ready to publish') else ''))
        with edit_button:
            if resumable or staged:
                st.button('Edit', key=key+'-edit', disabled=True, help='Edit '+title)
            else:
                _edit_link(source, title)
        from os_accounts import can_delete_files
        if selectable and not staged and can_delete_files(user):
            with delete_button:
                with st.container(key='design-review-delete-'+card_key):
                    remove = st.button('Delete', key=card_key+'-delete', help='Delete '+title,
                                       disabled=False)
            if remove:
                st.session_state['_review_delete_selection'] = [(source, title)]
                st.rerun()
        sport_picker = st.empty() if needs_sport else None
        clicked = False
        ad_clicked = False
        ad_mode = key+'-publish-ad-options'
        if published and row['data'].get('product_url'):
            publish.link_button('Open listing', row['data']['product_url'], key=key+'-shopify')
        else:
            clicked = publish.button('Add to queue', key=key+'-approved', type='primary',
                                     disabled=published or editing or staged, help=f'Add {title} to the upload queue')
            from os_accounts import can_access_page
            if all(can_access_page(user, page) for page in ('Ads', 'Posting', 'Files')):
                ad_clicked = publish_ad.button('Publish + ad', key=key+'-approved-ad',
                                             disabled=published or editing or staged,
                                             help='Add the design to the upload queue, then create a paused Meta Instant Experience campaign after publication.')
        if ad_clicked:
            st.session_state[ad_mode] = True
        if (clicked or ad_clicked) and needs_sport:
            st.session_state[key+'-needs-sport'] = True
            if clicked:
                st.session_state[key+'-pending-publish'] = True
        if sport_picker is not None and st.session_state.get(key+'-needs-sport'):
            from sports_categories import CANONICAL_SPORT_CATEGORIES
            chosen_sport = sport_picker.selectbox('Sport for ' + title, CANONICAL_SPORT_CATEGORIES,
                                                  index=None, placeholder='Choose a sport', key=key+'-sport')
            if not chosen_sport:
                st.info('Choose a sport below to finish adding this design to the upload queue.')
        if chosen_sport and st.session_state.get(key+'-pending-publish'):
            clicked = True
        ad_country = None
        if st.session_state.get(ad_mode) and not clicked and not (published or editing or staged):
            from design_publish_ad import COUNTRIES, primary_country
            ad_country = primary_country(details)
            if not ad_country:
                ad_country = st.selectbox('Ad country for '+title, tuple(COUNTRIES), index=None,
                                          placeholder='Choose a country', key=key+'-ad-country')
                ad_clicked = st.button('Queue publish + ad', key=key+'-confirm-ad',
                                       disabled=not ad_country or (needs_sport and not chosen_sport))
            elif needs_sport and ad_country:
                st.caption(f'Ad country: {ad_country}')
                ad_clicked = st.button('Queue publish + ad', key=key+'-confirm-ad',
                                       disabled=not chosen_sport)
        if (clicked or (ad_clicked and ad_country)) and (not needs_sport or chosen_sport):
            # Consume only once; a failed request needs an explicit retry.
            st.session_state.pop(key+'-pending-publish', None)
            from product_upload_staff_queue import enqueue
            # Consume the pending click even if the queue is unavailable. A later
            # unrelated rerun must not silently retry a failed enqueue.
            st.session_state.pop(key+'-needs-sport', None)
            try:
                if clicked:
                    job_id = enqueue(user, source, title, chosen_sport or details.get('sport'))
                    text = f'Added to upload queue · {title}'
                else:
                    job_id = enqueue(user, source, title, chosen_sport or details.get('sport'), ad_country=ad_country)
                    text = f'Added to upload and ad queue · {title}'
                st.session_state.pop(ad_mode, None)
                notice = dict(id=str(job_id), job_id=str(job_id), interaction_id=uuid.uuid4().hex,
                              kind='success', text=text, title=title, open_upload=False)
            except ValueError as exc:
                notice = dict(id=uuid.uuid4().hex, kind='error', text=str(exc))
            except Exception:
                logging.getLogger(__name__).exception('Smart Upload could not queue the design')
                action = 'Add to queue' if clicked else 'Publish + ad'
                notice = dict(id=uuid.uuid4().hex, kind='error',
                              text=f'Upload could not be queued. Your PSD is retained. Try {action} again.')
            st.session_state['_product_upload_notice'] = notice
            st.session_state[key+'-queue-notice'] = notice
            if notice['kind'] == 'success':
                st.session_state.pop(key+'-needs-sport', None)
        notice = st.session_state.get(key+'-queue-notice')
        if notice:
            getattr(st, notice['kind'])(notice['text'] + (' — view the queue in Uploads.' if notice['kind'] == 'success' else ''))
            if notice['kind'] == 'success':
                from product_upload_gallery import render as render_upload_component
                render_upload_component(key=key+'-queue-wake', mode='queue-wake',
                                        handoff={'id': notice['id']})
        if show_replacement and editing and not resumable and not staged:
            _staged_replacement(user, source, key)
            _keep_original(user, source, key)


def _published(user, query):
    from product_upload_api import connect
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, data->>'product_title' AS title, data->>'product_url' AS url,
                      data->'master_mapping_pending' AS mapping_pending
               FROM product_upload_intakes WHERE actor_id=%s
               AND data->'design_review'->>'decision' IN ('approved', 'preparing')
               AND data->>'product_gid' IS NOT NULL
               AND data->>'shopify_completion' IN ('Published live', 'Listing updated')
               ORDER BY updated_at DESC""",
            (str(user['id']),),
        )
        results = [row for row in cur.fetchall()
                   if query in (row['title'] or 'Confirmed Shopify product').casefold()]
    if not results:
        st.caption('No published gallery designs have been confirmed for this account.')
    for result in results:
        title = result['title'] or 'Confirmed Shopify product'
        if result['url']:
            st.link_button(title, result['url'], key=f"published-{result['id']}")
        else:
            st.write(title)
        if result['mapping_pending']:
            st.caption('Edition master replacement pending in Edition Ops.')


@st.cache_data(ttl=45, max_entries=16, show_spinner=False)
def _folder(actor_id):
    from product_upload_api import Dropbox
    provider = Dropbox()
    entries, working, backups, sidecars = {}, set(), set(), {}
    handoff_folder_found = False
    for entry in _folder_entries(provider, REVIEW):
        if final_psd(entry):
            entries[entry['id']] = entry
        elif entry.get('.tag') == 'folder':
            if (entry.get('path_display') or '').casefold() == REVIEW_METADATA_FOLDER.casefold():
                handoff_folder_found = True
        elif entry.get('.tag') == 'file':
            name = entry.get('name', '')
            if is_refresh_staging(name) and entry.get('rev') and approved(entry):
                entries[entry['id']] = entry
            if name.lower().endswith('.upload.json') and entry.get('path_display'):
                sidecars[entry['path_display'].casefold()] = entry
            stem, marked, edit = name.rpartition(' - EDIT-')
            if marked:
                revision, _, stage = edit.partition(' - ')
                kind = PurePosixPath(stage).stem.split(' - ', 1)[0]
                if kind in ('TRIAL', 'STAGING'):
                    working.add((stem, revision))
                elif kind == 'BACKUP':
                    backups.add((stem, revision))
    if handoff_folder_found:
        for entry in _folder_entries(provider, REVIEW_METADATA_FOLDER):
            if (entry.get('.tag') == 'file' and entry.get('path_display')
                    and entry.get('name', '').lower().endswith('.upload.json')):
                sidecars[entry['path_display'].casefold()] = entry
    ordered = sorted(entries.values(), key=lambda item: str(item.get('server_modified', '')), reverse=True)
    sidecars_by_path = [tuple(sidecars[p.casefold()] for p in handoff_paths(entry['path_display'])
                              if p.casefold() in sidecars) for entry in ordered]
    active_stems = {stem for stem, _ in working}
    designs, pending = [], {}
    for i, (entry, sidecars) in enumerate(zip(ordered, sidecars_by_path)):
        stem = PurePosixPath(entry['name']).stem
        editing = (stem, entry['rev']) in working or (stem, entry['rev']) in backups
        designs.append((entry, legacy_metadata(entry), '', editing) if not sidecars else None)
        if sidecars:
            pending[i] = _HANDOFF_POOL.submit(_synced_design, provider, actor_id, entry, sidecars,
                                              editing, editing or stem in active_stems)
    for i, task in pending.items():
        designs[i] = task.result()
    return designs, datetime.now(timezone.utc)


def _enqueue_selected(user, selected, fallback_sport=None):
    from product_upload_api import Dropbox
    from product_upload_staff_queue import enqueue
    from os_accounts import can_access_page, can_attach_missing_psd
    if not can_attach_missing_psd(user) or not all(can_access_page(user, page) for page in ('Files', 'Product Uploads')):
        raise PermissionError('Files and Product Uploads access is required to queue designs.')
    provider = Dropbox()
    queued, warnings = [], []
    for source, details in selected:
        title = details.get('design_name') or PurePosixPath(source['name']).stem
        try:
            actual = provider.metadata_if_present(source['id'])
            if not final_psd(source) or not actual or any(actual.get(field) != source.get(field) for field in ('id', 'rev', 'path_display')):
                raise ValueError('The PSD changed in Dropbox. Refresh before queueing it.')
            sport = details.get('sport') or fallback_sport
            if not sport:
                raise ValueError('Choose a sport before queueing this design.')
            queued.append((source, enqueue(user, actual, title, sport)))
        except ValueError as error:
            warnings.append(f'{title}: {error}')
        except Exception:
            logging.getLogger(__name__).exception('Could not queue selected Review PSD %s', source['id'])
            warnings.append(f'{title}: Upload queue unavailable. The PSD is retained.')
    return queued, warnings


def _selection_actions(user, selected):
    from os_accounts import can_delete_files
    from sports_categories import CANONICAL_SPORT_CATEGORIES
    with st.container(key='design-review-selection'):
        count, queue, trash = st.columns((8, 1, 1), vertical_alignment='center')
        count.caption(f'{len(selected)} selected')
        fallback = None
        if any(not details.get('sport') for _, details in selected):
            fallback = st.selectbox('Sport for designs without a sport', CANONICAL_SPORT_CATEGORIES,
                                    index=None, placeholder='Choose a sport', key='design-review-bulk-sport')
        missing_sport = any(not details.get('sport') for _, details in selected) and not fallback
        if queue.button('Add to queue', key='design-review-enqueue',
                        help=f'Add {len(selected)} selected designs to the Upload Companion queue',
                        disabled=not selected or missing_sport):
            try:
                with st.spinner('Adding selected designs to the upload queue'):
                    queued, warnings = _enqueue_selected(user, selected, fallback)
            except (ValueError, PermissionError) as error:
                st.error(str(error))
            except Exception:
                logging.getLogger(__name__).exception('Selected upload queue unavailable')
                st.error('Upload queue unavailable. Your designs are retained.')
            else:
                for source, _ in queued:
                    st.session_state.pop(_selection_key(source), None)
                st.session_state['_review_queue_result'] = (len(queued), warnings)
                st.rerun()
        if can_delete_files(user) and trash.button('', icon=':material/delete:', key='design-review-trash',
                                                  help=f'Delete {len(selected)} selected designs from Dropbox Review',
                                                  disabled=not selected):
            st.session_state['_review_delete_selection'] = [
                (source, details.get('design_name') or PurePosixPath(source['name']).stem)
                for source, details in selected]


@st.fragment
def _gallery(app, user):
    from product_upload_api import connect
    actor = str(user['id'])
    selection_only = st.session_state.pop('_review_selection_only', False)
    snapshot = st.session_state.get('_review_gallery_snapshot')
    with st.container(key='design-review-header'):
        heading, sync, refresh = st.columns((5, 1.5, 1), vertical_alignment='center')
        heading.title('Design Studio')
    publish_notice = st.session_state.pop('_review_publish_notice', None)
    if publish_notice:
        if publish_notice['kind'] == 'error':
            st.error(publish_notice['text'])
        else:
            st.success(publish_notice['text'] + ' · Keep adding designs here; view the queue in Uploads above.')
    removed = st.session_state.pop('_review_delete_result', None)
    if removed:
        count, warnings = removed
        if count:
            st.toast(f'Moved {count} design{"s" if count != 1 else ""} to Dropbox Deleted Files.')
        for warning in warnings:
            st.warning(warning)
    queued = st.session_state.pop('_review_queue_result', None)
    if queued:
        count, warnings = queued
        if count:
            st.toast(f'{count} selected design{"s" if count != 1 else ""} submitted to Upload Companion. Existing requests are reused.')
        for warning in warnings:
            st.warning(warning)
    result = st.session_state.pop('_review_replace_result', None)
    if result:
        path, warnings = result
        st.success('Verified replacement saved: ' + PurePosixPath(path).name)
        st.session_state['design-review-view'] = 'Review'
        for warning in warnings:
            st.warning(warning)
    kept = st.session_state.pop('_review_keep_result', None)
    if kept:
        name, warnings = kept
        if warnings:
            st.info('Original kept: ' + name)
            for warning in warnings:
                st.warning(warning)
        else:
            st.success('Original kept and selected drafts removed: ' + name)
            st.session_state['design-review-view'] = 'Review'
    with st.container(key='design-review-toolbar'):
        tabs, create, sport = st.columns((1, 1.5, 1))
        view = tabs.segmented_control('Designs', ('Review', 'Editing', 'Published'), default='Review',
                                      key='design-review-view', label_visibility='collapsed') or 'Review'
        create.html('<a class="sc-review-create" href="#create-design" data-design-create="true" role="button">Create design</a>')
        query = ''
    if view == 'Published':
        _published(user, query)
        return
    from sports_categories import CANONICAL_SPORT_CATEGORIES
    picked = sport.selectbox('Sport', ('All sports', *CANONICAL_SPORT_CATEGORIES), label_visibility='collapsed')
    if refresh.button('Refresh', help='Check Dropbox for new designs and revisions.'):
        _folder.clear(actor)
        selection_only = False
    context = (actor, view, query, picked)
    reuse = bool(selection_only and snapshot and snapshot['context'] == context)
    try:
        designs, synced = (snapshot['designs'], snapshot['synced']) if reuse else _folder(actor)
    except Exception:
        logging.getLogger(__name__).exception('Design Review gallery unavailable')
        st.warning('Review folder sync failed. Select Refresh to try again.')
        return
    ago = int((datetime.now(timezone.utc) - synced).total_seconds())
    sync.caption('Synced just now' if ago < 15 else f'Synced {ago}s ago')
    matched = [(entry, details, reason, editing) for entry, details, reason, editing in designs
               if (view != 'Editing' or editing)
               and (query in entry['name'].casefold() or query in (details.get('design_name') or '').casefold())
               and (picked == 'All sports' or details.get('sport') == picked)]
    if not matched:
        st.info('No PSDs match this view.')
        return
    selectable = view == 'Review'
    if selectable:
        selected = [(entry, details)
                    for entry, details, _, _ in matched
                    if final_psd(entry) and st.session_state.get(_selection_key(entry))]
        # Keep this container mounted: inserting it on selection shifts Streamlit's
        # delta paths and can temporarily apply toolbar styles to the artwork grid.
        _selection_actions(user, selected)
        pending_delete = st.session_state.get('_review_delete_selection')
        if pending_delete:
            _confirm_delete(user, pending_delete)
    sources = {review_key(entry): entry for entry, *_ in matched}
    rows = snapshot['rows'] if reuse else Intakes(connect).read_review_gallery(actor, sources)
    st.session_state['_review_gallery_snapshot'] = dict(
        context=context, designs=designs, synced=synced, rows=rows)
    keys = list(sources)
    with st.container(key='design-review-grid'):
        for offset in range(0, len(matched), 2):
            columns = st.columns(2)
            for i, (column, (entry, details, reason, editing)) in enumerate(zip(columns, matched[offset:offset+2]), start=offset):
                key = keys[i]
                with column:
                    _card(app, user, entry, details, reason, key, rows.get(key), editing=editing,
                          eager=i < 2, show_replacement=view == 'Editing', selectable=selectable)


def render(app, user):
    from product_upload_services import enabled
    css = Path(__file__).parent/'components/design_review_gallery.css'
    st.html(css.read_text(encoding='utf-8-sig'))
    st.html(css.with_name('design_review_edit.html'), unsafe_allow_javascript=True)
    with st.container(key='design-review-gallery'):
        if not all(app.os_accounts.can_access_page(user, name) for name in ('Files', 'Product Uploads')):
            st.title('Design Studio')
            st.info('Review requires Files and Product Uploads access.')
        elif not enabled() or not app.os_accounts.can_attach_missing_psd(user):
            st.title('Design Studio')
            st.info('Your account does not have access to the Product Uploads handoff.')
        else:
            _gallery(app, user)
    with st.expander('Advanced'):
        if st.toggle('Show design creation tools', key='design-review-advanced'):
            app.get_design_studio_page().render_design_studio_page(
                can_edit_prompts=app.prompt_editing_allowed(), user=user)
