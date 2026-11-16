"""Design Studio gallery for the exact PSDs in the Dropbox review folder."""
from datetime import datetime, timezone
from html import escape
from pathlib import PurePosixPath
import logging

import streamlit as st

from design_review_metadata import is_trial, legacy_metadata, read_handoff, review_key
from product_upload_dropbox import REVIEW, approved, select, within
from product_upload_intake import Intakes, action_mode


def final_psd(entry):
    return bool(approved(entry) and within(entry['path_display'], REVIEW)
                and entry.get('rev')
                and not is_trial(entry['name']))


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
    return 'Ready' if details.get('review_status') == 'ready_for_review' else 'Needs attention'


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
        details = read_handoff(provider, current)
        if not details or details['review_status'] != 'ready_for_review':
            raise ValueError('Resolve the revision checks and upload metadata before publishing.')
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


@st.dialog('Artwork preview', width='large')
def _zoom(preview, title):
    st.image(preview, caption=title, use_container_width=True)


def _card(app, provider, user, source):
    from product_upload_api import connect
    from product_upload_jobs import JOBS
    key = review_key(source)
    row = Intakes(connect).read_review(key, user['id'], source)
    if row:
        key = str(row['id'])
    job = JOBS.snapshot(key, user['id'], 'generate')
    try:
        details = read_handoff(provider, source) or legacy_metadata(source)
        reason = '' if details.get('upload_intent') else 'Add verified category and upload metadata for this PSD.'
    except ValueError as exc:
        details, reason = legacy_metadata(source), str(exc)
    except Exception:
        details, reason = legacy_metadata(source), 'Upload metadata could not be read for this PSD.'
    title = details.get('design_name') or PurePosixPath(source['name']).stem
    current = status(row, job, details)
    with st.container(border=True):
        preview = None
        try:
            preview = _thumbnail(str(user['id']), source['id'], source['rev'])
            st.image(preview, use_container_width=True)
        except Exception:
            st.caption('Preview unavailable for this revision.')
        st.markdown(f'<h3>{escape(title)}</h3>', unsafe_allow_html=True)
        st.caption(' · '.join(filter(None, (details.get('sport'), current))))
        target = details.get('shopify_product_id')
        if target:
            st.write('Refresh of linked product ' + target.rsplit('/', 1)[-1])
        elif details.get('upload_intent') == 'new_product':
            st.write('New product')
        if details.get('intended_collections'):
            st.caption('Collections: ' + ', '.join(details['intended_collections']))
        if reason or details.get('review_notes'):
            st.caption(reason or details['review_notes'])
        if job and job['state'] == 'Failed':
            st.warning(job.get('error') or 'Mockup generation failed.')
        if preview and st.button('Zoom artwork', key=key+'-zoom'):
            _zoom(preview, title)
        published = bool(row and row['data'].get('product_gid'))
        if published and row['data'].get('product_url'):
            st.link_button('Open Shopify product', row['data']['product_url'], key=key+'-shopify')
        if published and row['data'].get('master_mapping_pending'):
            st.caption('Shopify listing updated. The existing edition master remains linked pending the Edition Ops replacement workflow.')
        review_decision = ((row or {}).get('data', {}).get('design_review') or {}).get('decision')
        if (preview and not details.get('upload_intent') and not published and not review_decision
                and st.button('Open Smart Upload for classification', key=key+'-classify')):
            from product_upload_api import Dropbox
            from product_upload_jobs import prepare
            try:
                selected = select(connect, provider, key, user['id'], 'SMART', source['id'], source['rev'])
                prepare(connect, str(selected['id']), user['id'], Dropbox)
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.warning('This PSD could not be opened in Product Uploads. Try again.')
            else:
                app.set_current_page('Product Uploads', source='design_studio')
                st.query_params['upload'] = str(selected['id'])
                st.rerun()
        choices = st.columns(3)
        ready = bool(preview and details.get('review_status') == 'ready_for_review')
        resumable = current in ('Generating mockups', 'Mockups ready', 'Ready for Shopify handoff')
        label = 'Open Product Uploads' if resumable else 'Publish now'
        actions = ((label, 'approved'), ('Request changes', 'changes'), ('Reject', 'rejected'))
        for column, (label, command) in zip(choices, actions):
            disabled = published or (not ready if command == 'approved' else current == 'Generating mockups')
            if column.button(label, key=key+'-'+command, disabled=disabled):
                try:
                    if command != 'approved' or not resumable:
                        key = _review(app, provider, user, source, command)
                except ValueError as exc:
                    st.error(str(exc))
                    continue
                except Exception:
                    logging.getLogger(__name__).exception('Design review action failed')
                    st.error('The requested action could not be started. Your PSD is retained.')
                    continue
                if command == 'approved':
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


def render(app, user):
    from product_upload_api import Dropbox
    from product_upload_services import enabled
    st.title('Design Studio')
    st.subheader('Review gallery')
    if not all(app.os_accounts.can_access_page(user, name) for name in ('Files', 'Product Uploads')):
        st.info('Review requires Files and Product Uploads access.')
    elif not enabled() or not app.os_accounts.can_attach_missing_psd(user):
        st.info('Your account does not have access to the Product Uploads handoff.')
    else:
        cursor_key = '_design_review_cursor'
        if st.button('Refresh Review folder'):
            st.session_state.pop(cursor_key, None)
        try:
            provider = Dropbox()
            page = folder_page(provider, st.session_state.get(cursor_key, ''))
            entries = sorted((entry for entry in page['entries'] if final_psd(entry)),
                             key=lambda entry: str(entry.get('server_modified', '')), reverse=True)
            if not entries:
                st.info('No final PSDs on this page in the Review folder.')
            columns = st.columns(2)
            for index, entry in enumerate(entries):
                with columns[index % len(columns)]:
                    _card(app, provider, user, entry)
            if page.get('has_more') and page.get('cursor') and st.button('Next page'):
                st.session_state[cursor_key] = page['cursor']
                st.rerun()
            with st.expander('Published designs'):
                _published(user)
        except Exception:
            logging.getLogger(__name__).exception('Design Review gallery unavailable')
            st.warning('The Review folder could not be loaded. Refresh the gallery to retry.')
    with st.expander('Advanced'):
        if st.toggle('Show design creation tools', key='design-review-advanced'):
            app.get_design_studio_page().render_design_studio_page(
                can_edit_prompts=app.prompt_editing_allowed(), user=user)
