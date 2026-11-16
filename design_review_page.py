"""Design Studio gallery for the exact PSDs in the Dropbox review folder."""
import base64
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode
import logging

import streamlit as st

from design_review_metadata import is_working_file, legacy_metadata, read_handoff, review_key
from product_upload_dropbox import REVIEW, approved, select, within
from product_upload_intake import Intakes, action_mode


def final_psd(entry):
    return bool(approved(entry) and within(entry['path_display'], REVIEW)
                and entry.get('rev')
                and not is_working_file(entry['name']))


def folder_page(provider, cursor):
    return provider.api.list_folder_page(provider.token, REVIEW, cursor=cursor, limit=20)


@st.cache_data(ttl=120, max_entries=48, show_spinner=False)
def _thumbnail(actor_id, file_id, revision):
    from product_upload_api import Dropbox
    provider = Dropbox()
    return provider.api.get_psd_thumbnail_bytes(provider.token, file_id, revision=revision)


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


def _review(app, provider, user, entry, command):
    from product_upload_api import connect, Dropbox
    from product_upload_jobs import JOBS, generate
    from product_upload_export import folder_sport, sport_categories
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
        details = read_handoff(provider, current) or legacy_metadata(current)
        if details['review_status'] == 'needs_attention':
            raise ValueError(details.get('review_notes') or 'This saved revision has unresolved verification or metadata checks.')
        if not details.get('sport'):
            raise ValueError('The sport could not be resolved from this PSD or its metadata.')
        if details.get('shopify_product_id'):
            from shopify_sync import fetch_product_by_shopify_id
            target = fetch_product_by_shopify_id(details['shopify_product_id'])
            if target.get('shopify_product_id') != details['shopify_product_id'] or target.get('status') not in ('ACTIVE', 'DRAFT'):
                raise ValueError('The exact Shopify refresh target is unavailable.')
        token = app._files_access_token()
        root = app._files_team_root(token)
        sport = folder_sport(details['sport'])
        choices = [folder for folder in sport_categories(app.dropbox_integration, token, root)
                   if folder['sport'].casefold() == sport.casefold()]
        if len(choices) != 1:
            raise ValueError('The sport does not resolve to a single Product Uploads destination.')
    if not existing:
        existing = select(connect, provider, key, actor, 'SMART' if command == 'approved' else 'LIVE',
                          entry['id'], entry['rev'])
    key = str(existing['id'])
    job = JOBS.snapshot(key, actor, 'generate')
    if command == 'approved' and action_mode(existing) != 'SMART':
        store.change_mode(key, actor, 'SMART', metadata=details)
    with store.locked(key, actor) as (row, _):
        if row['data']['source']['rev'] != entry['rev']:
            raise ValueError('This intake belongs to another artwork revision.')
        if row['data'].get('product_gid'):
            return key
        row['data']['design_review'] = dict(decision=command, at=datetime.now(timezone.utc).isoformat())
        if command == 'approved' and row['data'].get('metadata') != details:
            raise ValueError('The upload metadata changed. Review the exact PSD again.')
    if command == 'approved' and not row['data'].get('mockups_exported') and (job or {}).get('state') != 'Ready':
        def finalize(result):
            return app.rebuild_result_artifacts(app.ensure_lifestyle_prompts(result))
        generate(connect, row, actor, details['design_name'], choices[0]['sport'], Dropbox,
                 app.BASE_DIR, app.MOCKUPS_GENERATION_SEMAPHORE, app.build_mockup_final_prompt_items,
                 finalize=finalize, prepare_first=True)
    return key


def _artwork(app, preview, title):
    encoded = base64.b64encode(preview).decode('ascii')
    template = (Path(__file__).parent/'components/design_review_artwork.html').read_text(encoding='utf-8-sig')
    markup = template.replace('__TITLE__', escape(title, quote=True)).replace('__IMAGE__', 'data:image/jpeg;base64,' + encoded)
    app.get_components_module().html(markup, height=280, scrolling=False)


@st.dialog('Review & Improve', width='large')
def _edit_dialog(app, provider, user, source, details, preview):
    from home_morning_brief_actions import PROJECT_URL, _prompt
    title = details.get('design_name') or PurePosixPath(source['name']).stem
    prompt = _prompt(title, details.get('product_context') or 'Preserve the story in the original artwork.',
                     edit=dict(source=source, metadata=details))
    st.caption('The project opens with a copied brief. Attach the preview and PSD, then paste and send the brief.')
    actions = st.columns(2)
    with actions[0]:
        if preview:
            st.download_button('Download preview', preview, title + '.jpg', mime='image/jpeg')
    with actions[1]:
        st.link_button('Download exact PSD', '/api/design-review/source?' + urlencode(
            dict(id=source['id'], rev=source['rev'])))
    payload = json.dumps(prompt).replace('<', r'\u003c')
    project = json.dumps(PROJECT_URL)
    app.get_components_module().html(
        """<style>body{margin:0;font:14px system-ui;color:#39332c}button{background:#8d6923;color:white;
        border:0;border-radius:7px;padding:10px 14px;font:600 14px system-ui;cursor:pointer}
        button:focus-visible{outline:2px solid #44320f;outline-offset:3px}</style>
        <button id="copy" type="button">Copy brief and open Sports Cave Designs</button>
        <span id="state" role="status"></span><script>
        document.getElementById('copy').addEventListener('click',async()=>{
          let copied=false;
          try{const field=document.createElement('textarea');field.value=""" + payload + """;
          field.style.cssText='position:fixed;left:-9999px';document.body.append(field);
          field.select();copied=document.execCommand('copy');field.remove();}catch{}
          if(!copied){document.getElementById('state').textContent=' Copy failed. Use the brief below.';return;}
          window.open(""" + project + """,'_blank','noopener,noreferrer');
          document.getElementById('state').textContent=' Copied. Attach the files and send the brief.';
        });</script>""", height=52)
    with st.expander('Review brief and attachment fallback'):
        st.link_button('Open Sports Cave Designs', PROJECT_URL)
        st.code(prompt, language=None)
    with st.expander('Apply staged replacement'):
        st.caption('Use this when ChatGPT can stage the edit in Dropbox but cannot apply a revision-checked update.')
        stem = str(PurePosixPath(source['path_display']).with_suffix('')) + ' - EDIT-' + source['rev']
        trial = st.text_input('Trial PSD path', value=stem + ' - TRIAL.psd')
        staged = st.text_input('Staged final PSD path', value=stem + ' - STAGING.psd')
        number_checked = st.checkbox('I verified the live edition number updates in place and restored its value in the staged PSD.')
        if st.button('Apply staged replacement', type='primary', disabled=not number_checked):
            from design_review_replace import apply
            try:
                with st.spinner('Checking both saved files and replacing the exact revision'):
                    final, backup, warnings = apply(provider, source, trial, staged)
            except ValueError as error:
                st.error(str(error))
            except Exception:
                logging.getLogger(__name__).exception('Design Studio replacement failed')
                st.error('The replacement could not be confirmed. Check the original, backup and staged files before retrying.')
            else:
                _folder.clear(str(user['id']))
                st.session_state['_review_replace_result'] = (final['path_display'], warnings)
                st.rerun()


def _details(provider, source):
    try:
        details = read_handoff(provider, source) or legacy_metadata(source)
        return details, ''
    except ValueError as exc:
        return dict(legacy_metadata(source), review_status='needs_attention'), str(exc)
    except Exception:
        return dict(legacy_metadata(source), review_status='needs_attention'), 'Upload metadata could not be read for this PSD.'


def _card(app, provider, user, source, details, reason, *, editing=False):
    from product_upload_api import connect
    from product_upload_jobs import JOBS
    key = review_key(source)
    row = Intakes(connect).read_review(key, user['id'], source)
    if row:
        key = str(row['id'])
    job = JOBS.snapshot(key, user['id'], 'generate')
    title = details.get('design_name') or PurePosixPath(source['name']).stem
    current = status(row, job, details)
    if editing and current in ('Ready to publish', 'In review'):
        current = 'Editing'
    facts = details.get('verified_collection_facts') or {}
    description = ' · '.join(filter(None, (
        ', '.join(details.get('athletes', ())), details.get('sport'), facts.get('league'),
        ', '.join(facts.get('teams', ())),
    )))
    target = details.get('shopify_product_id')
    intent = (f'Updates product {target.rsplit("/", 1)[-1]}' if target else
              'New product' if details.get('upload_intent') == 'new_product' else '')
    with st.container(border=True):
        preview = None
        try:
            preview = _thumbnail(str(user['id']), source['id'], source['rev'])
            _artwork(app, preview, title)
        except Exception:
            st.caption('Preview unavailable for this revision.')
        st.html(f'<h3>{escape(title)}</h3><div class="sc-review-meta">{escape(description)}</div>'
                f'<div class="sc-review-status"><strong data-ready="{str(current == "Ready to publish").lower()}">'
                f'{escape(current)}</strong><span>{escape(intent)}</span></div>')
        if details.get('intended_collections'):
            st.caption(' · '.join(details['intended_collections']))
        if reason or details.get('review_notes'):
            st.caption(reason or details['review_notes'])
        if job and job['state'] == 'Failed':
            st.warning(job.get('error') or 'Mockup generation failed.')
        published = bool(row and row['data'].get('product_gid'))
        if published and row['data'].get('product_url'):
            st.link_button('Open Shopify product', row['data']['product_url'], key=key+'-shopify')
        resumable = current in ('Generating mockups', 'Mockups ready', 'Ready for Shopify handoff')
        edit_button, publish = st.columns((1, 1.3))
        if edit_button.button('Edit', key=key+'-edit', use_container_width=True, disabled=resumable):
            _edit_dialog(app, provider, user, source, details, preview)
        if publish.button('Publish now', key=key+'-approved', use_container_width=True,
                          type='primary', disabled=published or editing or (not preview and not resumable)):
            try:
                if not resumable:
                    key = _review(app, provider, user, source, 'approved')
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                logging.getLogger(__name__).exception('Smart Upload could not start')
                st.error('Smart Upload could not start. Your PSD is retained.')
            else:
                app.set_current_page('Product Uploads', source='design_studio')
                st.query_params['upload'] = key
                st.rerun()


def _published(user):
    from product_upload_api import connect
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, data FROM product_upload_intakes WHERE actor_id=%s
               AND data->'design_review'->>'decision'='approved'
               AND data->>'product_gid' IS NOT NULL
               AND data->>'shopify_completion' IN ('Published live', 'Listing updated')
               ORDER BY updated_at DESC LIMIT 20""",
            (str(user['id']),),
        )
        results = cur.fetchall()
    if not results:
        st.caption('No published gallery designs have been confirmed for this account.')
    for result in results:
        data = result['data']
        title = data.get('product_title') or 'Confirmed Shopify product'
        if data.get('product_url'):
            st.link_button(title, data['product_url'], key=f"published-{result['id']}")
        else:
            st.write(title)
        if data.get('master_mapping_pending'):
            st.caption('Edition master replacement pending in Edition Ops.')


@st.cache_data(ttl=45, max_entries=16, show_spinner=False)
def _folder(actor_id):
    from product_upload_api import Dropbox
    provider = Dropbox()
    cursor, entries, seen, working = '', [], set(), []
    for _ in range(10):
        page = folder_page(provider, cursor)
        entries.extend(entry for entry in page['entries'] if final_psd(entry))
        working.extend(entry.get('name', '') for entry in page['entries']
                       if entry.get('.tag') == 'file' and ' - EDIT-' in entry.get('name', '')
                       and (' - TRIAL' in entry['name'] or ' - STAGING' in entry['name']))
        if not page.get('has_more'):
            break
        cursor = page.get('cursor')
        if not cursor or cursor in seen:
            raise ValueError('Review folder pagination could not be completed.')
        seen.add(cursor)
    ordered = sorted(entries, key=lambda item: str(item.get('server_modified', '')), reverse=True)
    editing = {entry['id'] for entry in ordered if any(
        name.startswith(PurePosixPath(entry['name']).stem + ' - EDIT-' + entry['rev'] + ' - ')
        for name in working
    )}
    return ordered, editing, datetime.now(timezone.utc), bool(page.get('has_more'))


@st.cache_data(ttl=45, max_entries=200, show_spinner=False)
def _cached_details(actor_id, source):
    from product_upload_api import Dropbox
    return _details(Dropbox(), source)


@st.fragment(run_every='50s')
def _gallery(app, user):
    from product_upload_api import Dropbox
    actor = str(user['id'])
    try:
        entries, editing, synced, partial = _folder(actor)
    except Exception:
        logging.getLogger(__name__).exception('Design Review gallery unavailable')
        st.warning('Review folder sync failed. The gallery will retry automatically.')
        return
    heading, sync = st.columns((3, 1))
    heading.title('Design Studio')
    ago = int((datetime.now(timezone.utc) - synced).total_seconds())
    sync.caption('● Synced just now' if ago < 15 else f'● Synced {ago}s ago')
    result = st.session_state.pop('_review_replace_result', None)
    if result:
        path, warnings = result
        st.success('Verified replacement saved: ' + PurePosixPath(path).name)
        for warning in warnings:
            st.warning(warning)
    page, search, sport = st.columns((1, 1.5, 1))
    view = page.segmented_control('Designs', ('Review', 'Editing', 'Published'), default='Review',
                                  key='design-review-view', label_visibility='collapsed') or 'Review'
    query = search.text_input('Search designs', placeholder='Search designs…', label_visibility='collapsed')
    matched = []
    if view == 'Published':
        _published(user)
        return
    for entry in entries:
        if view == 'Editing' and entry['id'] not in editing:
            continue
        if query.strip() and query.strip().casefold() not in entry['name'].casefold():
            continue
        matched.append(entry)
    from sports_categories import CANONICAL_SPORT_CATEGORIES
    picked = sport.selectbox('Sport', ('All sports', *CANONICAL_SPORT_CATEGORIES), label_visibility='collapsed')
    if picked != 'All sports':
        matched = [entry for entry in matched if _cached_details(actor, entry)[0].get('sport') == picked]
    if partial:
        st.caption('Showing the first 200 entries from the Review folder.')
    if not matched:
        st.info('No PSDs match this view.')
        return
    limit = 8
    pages = (len(matched) + limit - 1) // limit
    index = st.selectbox('Page', range(1, pages+1)) - 1 if pages > 1 else 0
    provider = Dropbox()
    with st.container(key='design-review-grid'):
        window = matched[index*limit:(index+1)*limit]
        for offset in range(0, len(window), 2):
            columns = st.columns(2)
            for column, entry in zip(columns, window[offset:offset+2]):
                with column:
                    _card(app, provider, user, entry, *_cached_details(actor, entry),
                          editing=entry['id'] in editing)


def render(app, user):
    from product_upload_services import enabled
    css = Path(__file__).parent/'components/design_review_gallery.css'
    st.html(css.read_text(encoding='utf-8-sig'))
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
