"""Streamlit Wall Preview Inbox for shopper-created room previews."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import html
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

import streamlit as st

import dropbox_integration
import os_accounts
import social_media
import wall_preview_store
import wall_preview_identity
import wall_preview_crm_store
import wall_preview_deletion


_TEMP_LINK_CACHE = {}
_THUMBNAIL_CACHE = OrderedDict()
_THUMBNAIL_LOCK = Lock()
_THUMBNAIL_TTL = 120
_THUMBNAIL_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wall-thumbnails")


WALL_PREVIEW_DROPBOX_PATH = "/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox"


STATUS_LABELS = {
    "new": "New",
    "approved": "Approved",
    "used": "Used",
    "archived": "Archived",
    "all": "All",
}


@st.cache_resource(ttl=20 * 60, show_spinner=False)
def _dropbox_connection():
    return dropbox_integration.resolve_server_auth(validate=False)["access_token"]


def _temporary_link(path, file_id=""):
    now = time.monotonic()
    cached = _TEMP_LINK_CACHE.get(path) or {}
    if cached.get("url") and float(cached.get("expires_at") or 0) > now:
        return cached["url"]
    token = _dropbox_connection()
    try:
        url = dropbox_integration.get_temporary_link(token, path)
    except dropbox_integration.DropboxApiError:
        # IDs survive path/namespace changes and avoid creating shared links.
        if not file_id.startswith("id:"):
            raise
        result = dropbox_integration.team_space_client(token).files_get_temporary_link(file_id)
        url = str(result.link or "")
    _TEMP_LINK_CACHE[path] = {"url": url, "expires_at": now + 8 * 60}
    if len(_TEMP_LINK_CACHE) > 250:
        for key in list(_TEMP_LINK_CACHE)[:50]:
            if float((_TEMP_LINK_CACHE.get(key) or {}).get("expires_at") or 0) <= now:
                _TEMP_LINK_CACHE.pop(key, None)
    return url


def _format_received(value):
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(social_media.SYDNEY_TZ).strftime("%d %b %Y · %I:%M %p")
    except Exception:
        return str(value)


def _set_status(user, row, status):
    try:
        wall_preview_store.update_status(
            row.get("id"),
            status,
            actor_user_id=user.get("id"),
            include_private=os_accounts.is_admin(user),
        )
        _TEMP_LINK_CACHE.pop(str(row.get("dropbox_path") or ""), None)
        _page.clear()
        st.rerun()
    except wall_preview_store.WallPreviewStoreError as error:
        st.error(str(error))
    except Exception:
        st.error("This change could not be saved. Please retry.")


def _current_marketing(rows):
    """One cached, read-only batch for the visible customer matches, never consent writes."""
    identities = list({row.get('shopify_customer_id') for row in rows if row.get('shopify_customer_id')})
    if not identities:
        return {}
    try:
        customers = wall_preview_identity.crm_shopify.Shopify().customer_batch(identities[:50])
        return {customer['id']: customer for customer in customers}
    except Exception as error:
        logging.getLogger(__name__).warning('wall_preview_marketing_unavailable error_type=%s', type(error).__name__)
        return {}


def _details(user,row):
    if not os_accounts.is_admin(user) and not row.get('marketing_permission'):return
    key_prefix='wall-preview-'+str(row['id'])
    customer_name=row.get('customer_name') or ''
    customer_email=row.get('customer_email') or ''
    details = st.expander('Journey, permissions and workflow', key=key_prefix+'-journey', on_change='rerun')
    if not details.open:
        return
    with details:
        st.caption('Preview ID · '+str(row['id']))
        if row.get('client_preview_id'):st.caption('Client ID · '+str(row['client_preview_id']))
        if os_accounts.is_admin(user):
            st.caption('HD email · '+str(row.get('email_job_state') or ('Sent' if row.get('email_sent_at') else 'Requested' if row.get('email_requested_at') else 'Not requested')))
            st.caption('Follow-up flow · '+wall_preview_crm_store.FLOW_NAME)
            if row.get('shopify_customer_id'):
                customer_url=wall_preview_identity.customer_admin_url(row['shopify_customer_id'])
                if customer_url:st.link_button('Open Shopify customer',customer_url)
        st.caption(' · '.join(str(row.get(k) or '') for k in ('frame_label','size_label','market_country_name') if row.get(k)))
        st.caption('MARKETING USE: ALLOWED' if row.get('marketing_permission') else 'N/A')
        if row.get('email_marketing_state')=='SUBSCRIBED':st.caption('EMAIL: SUBSCRIBED')
        if row.get('market_country_code'):st.caption('MARKET: '+str(row.get('market_country_name') or '').upper()+' ('+str(row['market_country_code'])+')')
        st.markdown('**Journey**')
        st.caption(customer_name or customer_email or 'Anonymous visitor')
        try:
            for item in wall_preview_crm_store.timeline(str(row['id'])):
                st.caption(item['event_name'].removeprefix('WallPreview')+(' · '+str(item.get('size') or '') if item['event_name']=='WallPreviewSizeChanged' else ' · '+str(item.get('frame') or '') if item['event_name']=='WallPreviewFrameChanged' else '')+' · '+_format_received(item['occurred_at']))
        except Exception:st.caption('Timeline temporarily unavailable.')
        if row.get('share_token') and not row.get('share_revoked_at'):
            share_url='https://sports-cave-image-factory.onrender.com/wall-preview/'+row['share_token']
            st.link_button('Open share page',share_url)
            st.code(share_url,language=None)
            if os_accounts.is_admin(user) and st.button('Revoke share link',key=key_prefix+'-revoke'):
                wall_preview_crm_store.revoke_share(str(row['id']));st.rerun()
        if row.get('marketing_permission'):
            if st.button('Approve',key=key_prefix+'-approve'):_set_status(user,row,'approved')
            if st.button('Mark used',key=key_prefix+'-used'):_set_status(user,row,'used')
        if os_accounts.is_admin(user) or row.get('marketing_permission'):
            if st.button('Archive',key=key_prefix+'-archive'):_set_status(user,row,'archived')
        if st.button('Close details',key=key_prefix+'-close'):
            st.session_state.pop('wall-preview-details',None);st.rerun()



def _open_wall_preview_folder():
    clean_path=dropbox_integration.normalize_dropbox_path(WALL_PREVIEW_DROPBOX_PATH)
    st.session_state['files_browser_path']=clean_path
    st.session_state.pop('files_preview_path',None)
    st.session_state['current_page']='Files'
    st.session_state['selected_page']='Files'
    st.session_state['current_page_source']='wall-preview-inbox'
    st.query_params['page']='files'
    st.query_params['files_path']=clean_path
    for key in ('files_preview','files_action','files_selected'):
        if key in st.query_params:del st.query_params[key]
    st.rerun()



from pathlib import Path
import base64
import re
import streamlit.components.v1 as components

_gallery=components.declare_component('wall_preview_gallery',path=str(Path(__file__).parent/'components'/'wall_preview_gallery'))

def _clear_thumbnails():
    with _THUMBNAIL_LOCK:
        _THUMBNAIL_CACHE.clear()


def _thumbnails(assets):
    """Batch Dropbox cache misses. Keep only small, versioned thumbnails in memory."""
    now = time.monotonic()
    thumbnails, missing = {}, []
    with _THUMBNAIL_LOCK:
        for asset in assets:
            cached = _THUMBNAIL_CACHE.get(asset)
            if cached and cached[0] > now:
                thumbnails[asset[0]] = cached[1]
                _THUMBNAIL_CACHE.move_to_end(asset)
            else:
                missing.append(asset)
    if not missing:
        return thumbnails

    import dropbox
    client = dropbox_integration.team_space_client(_dropbox_connection()).clone(
        timeout=8, max_retries_on_error=0, max_retries_on_rate_limit=0)
    entries = [dropbox.files.ThumbnailArg(path=path, format=dropbox.files.ThumbnailFormat.jpeg,
        size=dropbox.files.ThumbnailSize.w256h256, mode=dropbox.files.ThumbnailMode.bestfit)
        for _, path, _ in missing]
    result = client.files_get_thumbnail_batch(entries)
    expires = time.monotonic() + _THUMBNAIL_TTL
    with _THUMBNAIL_LOCK:
        for asset, entry in zip(missing, result.entries):
            if entry.is_success():
                image = 'data:image/jpeg;base64,' + entry.get_success().thumbnail
                thumbnails[asset[0]] = image
                _THUMBNAIL_CACHE[asset] = (expires, image)
                _THUMBNAIL_CACHE.move_to_end(asset)
        while len(_THUMBNAIL_CACHE) > 384:
            _THUMBNAIL_CACHE.popitem(last=False)
    return thumbnails


@st.cache_data(ttl=30,show_spinner=False,max_entries=64)
def _page(**filters):
    return wall_preview_store.list_previews(cards_only=True, **filters)


def _image(row):
    if row.get('dropbox_file_id'):
        _,content=dropbox_integration.get_file_bytes(_dropbox_connection(),row['dropbox_path'])
        return content
    with wall_preview_crm_store.transaction() as cur:
        cur.execute('SELECT image FROM public.wall_preview_archive_jobs WHERE preview_id=%s',(str(row['id']),))
        return bytes((cur.fetchone() or {}).get('image') or b'')


def _reset():
    defaults={'wp-analytics-period':'30 Days','wp-analytics-product':'','wp-analytics-device':'All',
        'wp-analytics-capture':'All','wall-preview-intent':'All','wall-preview-inbox-status':'All',
        'wall-preview-customer-search':'','wall-preview-cursors':[None]}
    for key,value in defaults.items():st.session_state[key]=value
    st.session_state.pop('wp-analytics-custom',None)


def _delete_confirm(user, preview_ids):
    """Both dialogs use an immutable ID snapshot, never the current grid indices."""
    if not os_accounts.is_admin(user):
        st.error('Only administrators can delete previews.');return
    ids=wall_preview_deletion.validate_ids(preview_ids)
    count=len(ids)
    st.markdown(f'**Delete {count} Wall Preview{"s" if count != 1 else ""}?**')
    st.warning('This will permanently remove the selected previews and their associated files from Sports Cave OS and Dropbox. Shared files needed by other previews are kept. This action cannot be undone in Sports Cave OS.')
    running=bool(st.session_state.get('wall-preview-deleting'))
    error_message=st.session_state.pop('wall-preview-delete-error',None)
    if error_message:st.error(error_message)
    controls=st.empty()
    with controls.container():
        left,right=st.columns(2)
        cancel=left.button('Cancel',key='wp-delete-cancel',disabled=running)
        confirm=right.button(f'Delete {count} Preview{"s" if count != 1 else ""}',type='primary',key='wp-delete-confirm',disabled=running)
    if cancel:
        st.session_state.pop('wall-preview-delete',None);st.rerun()
    if confirm:
        st.session_state['wall-preview-deleting']=True
        controls.empty()
        progress=st.progress(0,text=f'Deleting 0 of {count} previews…')
        try:
            results=wall_preview_deletion.bulk_delete(ids,user=user,
                progress=lambda done,total:progress.progress(done/total,text=f'Processed {done} of {total} previews'))
            st.session_state['wall-preview-delete-results']=results
            st.session_state['wall-preview-selection-revision']=str(time.time_ns())
            _page.clear();_thumbnails.clear();_TEMP_LINK_CACHE.clear()
            from wall_preview_analytics_ui import snapshot
            snapshot.clear()
            st.session_state['wall-preview-cursors']=[None]
            st.session_state.pop('wall-preview-delete',None)
            st.session_state.pop('wall-preview-details',None)
        except Exception as error:
            st.session_state['wall-preview-delete-error']=str(error) if isinstance(error,wall_preview_store.WallPreviewStoreError) else 'Deletion could not finish. Please retry.'
            st.rerun(scope='fragment')
        finally:
            st.session_state['wall-preview-deleting']=False
        st.rerun()


@st.dialog('Delete Wall Previews',dismissible=False)
def _bulk_delete_dialog(user, preview_ids):
    st.session_state["wall-preview-dialog-open"] = True
    _delete_confirm(user, tuple(preview_ids))


@st.dialog('Wall Preview', width='large', on_dismiss='rerun')
def _viewer(user,preview_id,action='view'):
    st.session_state['wall-preview-dialog-open'] = True
    st.html("""<style>
    div:has(> [role="dialog"] .sc-wall-viewer){padding-top:0!important;height:100dvh!important}
    [role="dialog"]:has(.sc-wall-viewer){margin:12px auto!important;min-width:0!important;max-width:calc(100vw - 24px)!important;max-height:calc(100dvh - 24px)!important;overflow-y:auto!important}
    [data-testid="stElementContainer"]:has(.sc-wall-viewer){display:none}
    </style><div class="sc-wall-viewer"></div>""")
    row=wall_preview_store.get_preview(preview_id,include_private=os_accounts.is_admin(user))
    if not row:
        st.info('This preview is no longer available.');return
    st.markdown('**'+str(row.get('product_title') or 'Wall preview')+'**')
    st.caption(_format_received(row.get('received_at'))+' · '+str(row.get('customer_name') or row.get('customer_email') or 'Anonymous visitor')+' · '+str(row.get('status') or 'new'))
    if action=='delete' or st.session_state.get('wall-preview-delete')==preview_id:
        _delete_confirm(user, (preview_id,))
        return
    cached_image = st.session_state.get('wall-preview-viewer-image')
    image_key = (preview_id, row.get('version'), row.get('dropbox_file_id'))
    if cached_image and cached_image[0] == image_key:
        image = cached_image[1]
    else:
        try:
            content = _image(row)
            image = ('data:' + str(row.get('content_type') or 'image/jpeg') + ';base64,' +
                     base64.b64encode(content).decode()) if content else ''
        except Exception:
            image = ''
        if image:
            st.session_state['wall-preview-viewer-image'] = (image_key, image)
    extension='.png' if row.get('content_type')=='image/png' else '.jpg'
    filename='sports-cave-wall-preview-'+re.sub(r'[^a-z0-9-]+','-',str(row.get('product_handle') or 'artwork').lower())+'-'+str(row.get('received_at') or '')[:10]+extension
    viewer_event=_gallery(mode='viewer',id=preview_id,image=image,title=row.get('product_title'),filename=filename,
        key='wp-full-viewer',default=None)
    if (image and viewer_event and viewer_event.get('action')=='viewed' and viewer_event.get('id')==preview_id
            and viewer_event.get('nonce')!=st.session_state.get('wall-preview-viewed-event')):
        try:
            from wall_preview_notifications import mark_seen
            mark_seen(preview_id,user)
            st.session_state['wall-preview-viewed-event']=viewer_event['nonce']
        except Exception:
            st.warning('Image opened, but its unread status could not be saved. Reopen it to retry.')
    if viewer_event and viewer_event.get('action')=='close' and viewer_event.get('nonce')!=st.session_state.get('wall-preview-viewer-event'):
        st.session_state['wall-preview-viewer-event']=viewer_event['nonce'];st.rerun()
    if os_accounts.is_admin(user) and st.button('Delete image',key='wp-delete-open'):
        st.session_state['wall-preview-delete']=preview_id;st.rerun(scope='fragment')
    _details(user,row)


def _gallery_with_thumbnails(assets, items, **options):
    job = st.session_state.get('wall-preview-thumbnail-job')
    now = time.monotonic()
    if job is None or job[0] != assets or (job[1] is not None and job[1].done() and now >= job[2]):
        if job is not None and job[1] is not None:
            job[1].cancel()
        future = _THUMBNAIL_WORKERS.submit(_thumbnails, assets) if assets else None
        job = (assets, future, now + _THUMBNAIL_TTL)
        st.session_state['wall-preview-thumbnail-job'] = job
    future = job[1]
    pending = future is not None and not future.done()

    thumbnails = {}
    if pending:
        @st.fragment(run_every=0.5)
        def wait_for_thumbnails():
            if future.done() and not st.session_state.get("wall-preview-dialog-open"):
                st.rerun()

        wait_for_thumbnails()
    elif future is not None:
        try:
            thumbnails = future.result()
        except Exception:
            st.caption('Thumbnails temporarily unavailable. Open a preview to retry.')
    cards = [dict(item, thumbnail=thumbnails.get(item['id'], '')) for item in items]
    return _gallery(items=cards, loadingThumbnails=pending, **options)


def _notifications(user):
    from wall_preview_notifications import inbox_status, mark_read

    try:
        status = inbox_status(user)
    except Exception:
        st.caption('Unread status is temporarily unavailable.')
        return
    unread = status['unread_count']
    if not unread:
        st.caption('No unread previews')
        return
    with st.popover(f'{unread} unread', icon=':material/notifications:'):
        if st.button('Mark all as read', key='wp-mark-all-read'):
            try:
                mark_read(user)
            except Exception:
                st.error('Couldn’t mark previews as read. Try again.')
            else:
                st.rerun()
        for notification in status['notifications']:
            preview_id = notification['wall_preview_id']
            if st.button(notification['subtitle'], key=f'wp-notification-{preview_id}', width='stretch'):
                return preview_id


def render(user):
    st.session_state.pop("wall-preview-dialog-open", None)
    st.session_state.pop("wall-preview-viewer-image", None)
    if not os_accounts.can_access_page(user,social_media.WALL_PREVIEW_ROUTE):
        st.caption('Wall Preview Inbox access is not approved for this account.');return
    from social_media_ui import inject_styles
    import wall_preview_analytics_ui as analytics
    inject_styles()
    st.markdown('<div class="sc-social-header"><h1>Wall Preview Inbox</h1><p>Customer wall previews from See It On Your Wall.</p></div>',unsafe_allow_html=True)
    notification_target = _notifications(user)
    target = st.query_params.get('wall_preview_id') or notification_target
    if target:
        if 'wall_preview_id' in st.query_params:
            del st.query_params['wall_preview_id']
        try:
            import uuid
            target=str(uuid.UUID(target))
        except (ValueError,TypeError):
            st.warning('This Wall Inbox image link is invalid.')
        else:
            _viewer(user,target)
    results=st.session_state.get('wall-preview-delete-results') or []
    if results:
        failed=[r for r in results if r['status']=='failed']
        succeeded=len(results)-len(failed)
        if not failed:st.success(f'{succeeded} previews deleted or already removed.')
        elif succeeded:st.warning(f'{succeeded} removed; {len(failed)} could not be deleted. Select failed previews to retry.')
        else:st.error('No previews were fully deleted. Review the errors and retry.')
        for result in failed:st.caption(result['id']+' · '+result['error'])
        if any(r.get('shared_files_preserved') for r in results):st.caption('Shared files still needed by other previews were preserved.')
        if st.button('Dismiss deletion results',key='wp-dismiss-deletion'):
            st.session_state.pop('wall-preview-delete-results',None);st.rerun()
    controls=st.columns([3,1,1])
    if controls[0].button('Open Wall Preview Folder',icon=':material/folder_open:',disabled=not os_accounts.can_access_page(user,'Files')):_open_wall_preview_folder()
    if controls[1].button('Refresh',icon=':material/refresh:'):
        job = st.session_state.pop('wall-preview-thumbnail-job', None)
        if job is not None and job[1] is not None:
            job[1].cancel()
        _page.clear();_clear_thumbnails();analytics.snapshot.clear()
        analytics.engagement.clear()
    controls[2].button('Reset filters',on_click=_reset)
    metrics = st.container()
    filters = analytics.report_filters()
    if filters is None:return
    with st.container(key='wp-inbox-filters'):
        cols=st.columns([1,1,2])
        status=cols[0].selectbox('Status',('All','New','Approved','Used','Archived'),key='wall-preview-inbox-status')
        intent=cols[1].selectbox('CRM intent',('All','Confirmed','Email captured','Added to cart','Purchased','Reuse allowed'),key='wall-preview-intent')
        search=cols[2].text_input('Search customer or product',key='wall-preview-customer-search',max_chars=254)
    filters.update(status=status.lower(),intent=intent.lower().replace(' ','_'),customer_search=search,include_private=os_accounts.is_admin(user),limit=25)
    signature=repr(sorted(filters.items()))
    if st.session_state.get('wall-preview-filter-signature')!=signature:
        st.session_state['wall-preview-cursors']=[None]
        st.session_state['wall-preview-filter-signature']=signature
    cursors=st.session_state.setdefault('wall-preview-cursors',[None])
    try:rows=_page(**filters,cursor=cursors[-1])
    except Exception:
        st.error('Couldn’t load Wall Preview Inbox. Use Refresh to retry.');return
    if not rows:
        st.info('No customer wall previews match these filters.')
        with metrics:
            analytics.render_metrics(filters)
        return
    visible=[r for r in rows[:24] if os_accounts.is_admin(user) or r.get("marketing_permission")]
    assets=tuple((str(r['id']),r['dropbox_file_id'] if str(r.get('dropbox_file_id')).startswith('id:') else r['dropbox_path'],str(r.get('version') or r.get('last_saved_at') or '')) for r in visible if r.get('dropbox_file_id'))
    items=[dict(id=str(r['id']),title=r.get('product_title') or r.get('product_id') or 'Wall preview',
        identity=(r.get('customer_email') if os_accounts.is_admin(user) else '') or r.get('customer_name') or 'Anonymous visitor',
        date=_format_received(r.get('received_at')),status='Deletion pending · retry' if (r.get('attribution') or {}).get('inbox_deletion') else STATUS_LABELS.get(r.get('status'),'New')) for r in visible]
    scope=signature+repr(cursors[-1])
    event = _gallery_with_thumbnails(assets, items, canDelete=os_accounts.is_admin(user), scope=scope,
        selectedIds=[r['id'] for r in results if r['status']=='failed'],
        selectionRevision=st.session_state.get('wall-preview-selection-revision'), key='wp-gallery', default=None)
    nav=st.columns([1,2,1])
    if nav[0].button('Previous',disabled=len(cursors)==1):
        cursors.pop();st.rerun()
    nav[1].caption(f'Page {len(cursors)} · {len(visible)} previews')
    if nav[2].button('Next',disabled=len(rows)<=24):
        last=visible[-1];cursors.append((str(last['received_at']),str(last['id'])));st.rerun()
    with metrics:
        analytics.render_metrics(filters)
    analytics.details(filters)
    if event and event.get('scope') == scope and event.get('nonce') != st.session_state.get('wall-preview-event'):
        st.session_state['wall-preview-event'] = event['nonce']
        if event.get('action') in ('bulk_read', 'bulk_delete'):
            ids = event.get('ids')
            visible_ids = {str(row['id']) for row in visible}
            if (event.get('scope') != scope or not isinstance(ids, list) or not 1 <= len(ids) <= 24
                    or any(not isinstance(value, str) or value not in visible_ids for value in ids)):
                return
            if event['action'] == 'bulk_delete':
                if os_accounts.is_admin(user):
                    _bulk_delete_dialog(user, tuple(dict.fromkeys(ids)))
            else:
                from wall_preview_notifications import mark_read
                try:
                    mark_read(user, ids)
                except Exception:
                    st.error('Couldn’t mark selected previews as read. Try again.')
                else:
                    st.session_state['wall-preview-selection-revision'] = event['nonce']
                    st.rerun()
            return
        if event.get('id') in {str(r['id']) for r in visible}:
            if event.get('action')=='delete':st.session_state['wall-preview-delete']=event['id']
            _viewer(user,event['id'],event.get('action','view'))
