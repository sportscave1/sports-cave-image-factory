"""Streamlit Wall Preview Inbox for shopper-created room previews."""

from __future__ import annotations

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


_TEMP_LINK_CACHE = {}


WALL_PREVIEW_DROPBOX_PATH = "/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox"


STATUS_LABELS = {
    "new": "New",
    "approved": "Approved",
    "used": "Used",
    "archived": "Archived",
    "all": "All",
}


def _dropbox_connection():
    cached = st.session_state.get("wall-preview-dropbox-token") or {}
    if cached.get("token") and float(cached.get("expires_at") or 0) > time.monotonic():
        return cached["token"]
    auth = dropbox_integration.resolve_server_auth(validate=False)
    token = auth["access_token"]
    st.session_state["wall-preview-dropbox-token"] = {
        "token": token,
        "expires_at": time.monotonic() + 20 * 60,
    }
    return token


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
    with st.expander('Journey, permissions and workflow'):
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

@st.cache_data(ttl=120,show_spinner=False,max_entries=24)
def _thumbnails(assets):
    """One Dropbox thumbnail batch; never download original photographs for cards."""
    if not assets:return {}
    import dropbox
    client=dropbox_integration.team_space_client(_dropbox_connection())
    entries=[dropbox.files.ThumbnailArg(path=path,format=dropbox.files.ThumbnailFormat.jpeg,
        size=dropbox.files.ThumbnailSize.w256h256,mode=dropbox.files.ThumbnailMode.bestfit) for _,path,_ in assets]
    result=client.files_get_thumbnail_batch(entries)
    return {str(identity):'data:image/jpeg;base64,'+entry.get_success().thumbnail
        for (identity,_,_),entry in zip(assets,result.entries) if entry.is_success()}

@st.cache_data(ttl=30,show_spinner=False,max_entries=64)
def _page(**filters):
    return wall_preview_store.list_previews(**filters)


def _remove_asset(row):
    token=_dropbox_connection()
    path=row['dropbox_path']
    if not dropbox_integration.path_is_within_root(path,WALL_PREVIEW_DROPBOX_PATH):
        raise ValueError('Unexpected preview location.')
    metadata=dropbox_integration.get_metadata_if_exists(token,path)
    if metadata:
        if row.get('dropbox_file_id'):
            if metadata.get('id')!=row['dropbox_file_id']:
                raise ValueError('Preview storage identity changed.')
        elif Path(path).stem not in {str(row['id']),str(row.get('client_preview_id'))}:
            # A worker may have uploaded before its database commit failed. Only
            # the exact capture-owned filename may be removed in that situation.
            raise ValueError('Unconfirmed preview storage identity.')
        dropbox_integration.delete_path_recoverable(token,path,root_path=WALL_PREVIEW_DROPBOX_PATH)


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


@st.dialog('Wall Preview',width='large')
def _viewer(user,preview_id,action='view'):
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
        st.warning('Delete wall preview? This removes this image from the Inbox and Dropbox. Analytics history is retained.')
        left,right=st.columns(2)
        if left.button('Cancel',key='wp-delete-cancel'):
            st.session_state.pop('wall-preview-delete',None);st.rerun()
        if right.button('Delete',type='primary',key='wp-delete-confirm'):
            try:
                wall_preview_store.delete_preview(preview_id,user=user,remove_asset=_remove_asset)
                _page.clear();_thumbnails.clear();st.session_state.pop('wall-preview-delete',None)
                st.session_state.pop('wall-preview-details',None);st.rerun()
            except Exception as error:
                logging.getLogger(__name__).warning('wall_preview_delete_failed preview_id=%s error_type=%s',preview_id,type(error).__name__)
                st.error('Could not delete this preview. Nothing else was selected. Please retry.')
        return
    try:
        content=_image(row)
        image='data:'+str(row.get('content_type') or 'image/jpeg')+';base64,'+base64.b64encode(content).decode() if content else ''
    except Exception:
        image=''
    extension='.png' if row.get('content_type')=='image/png' else '.jpg'
    filename='sports-cave-wall-preview-'+re.sub(r'[^a-z0-9-]+','-',str(row.get('product_handle') or 'artwork').lower())+'-'+str(row.get('received_at') or '')[:10]+extension
    viewer_event=_gallery(mode='viewer',id=preview_id,image=image,title=row.get('product_title'),filename=filename,key='wp-full-viewer',default=None)
    if viewer_event and viewer_event.get('action')=='close' and viewer_event.get('nonce')!=st.session_state.get('wall-preview-viewer-event'):
        st.session_state['wall-preview-viewer-event']=viewer_event['nonce'];st.rerun()
    if os_accounts.is_admin(user) and st.button('Delete image',key='wp-delete-open'):
        st.session_state['wall-preview-delete']=preview_id;st.rerun(scope='fragment')
    _details(user,row)


def render(user):
    if not os_accounts.can_access_page(user,social_media.WALL_PREVIEW_ROUTE):
        st.caption('Wall Preview Inbox access is not approved for this account.');return
    from social_media_ui import inject_styles
    from wall_preview_analytics_ui import render as analytics_render, snapshot
    inject_styles()
    st.markdown('<div class="sc-social-header"><h1>Wall Preview Inbox</h1><p>Customer wall previews from See It On Your Wall.</p></div>',unsafe_allow_html=True)
    controls=st.columns([3,1,1])
    if controls[0].button('Open Wall Preview Folder',icon=':material/folder_open:',disabled=not os_accounts.can_access_page(user,'Files')):_open_wall_preview_folder()
    if controls[1].button('Refresh',icon=':material/refresh:'):
        _page.clear();_thumbnails.clear();snapshot.clear()
    controls[2].button('Reset filters',on_click=_reset)
    filters=analytics_render()
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
        st.info('No customer wall previews match these filters.');return
    visible=[r for r in rows[:24] if os_accounts.is_admin(user) or r.get("marketing_permission")]
    assets=tuple((str(r['id']),r['dropbox_file_id'] if str(r.get('dropbox_file_id')).startswith('id:') else r['dropbox_path'],str(r.get('version') or r.get('last_saved_at') or '')) for r in visible if r.get('dropbox_file_id'))
    try:thumbs=_thumbnails(assets)
    except Exception:
        thumbs={};st.caption('Thumbnails temporarily unavailable. Open a preview to retry.')
    items=[dict(id=str(r['id']),title=r.get('product_title') or r.get('product_id') or 'Wall preview',
        identity=(r.get('customer_email') if os_accounts.is_admin(user) else '') or r.get('customer_name') or 'Anonymous visitor',
        date=_format_received(r.get('received_at')),status=STATUS_LABELS.get(r.get('status'),'New'),thumbnail=thumbs.get(str(r['id']),'')) for r in visible]
    event=_gallery(items=items,canDelete=os_accounts.is_admin(user),key='wp-gallery',default=None)
    nav=st.columns([1,2,1])
    if nav[0].button('Previous',disabled=len(cursors)==1):
        cursors.pop();st.rerun()
    nav[1].caption(f'Page {len(cursors)} · {len(visible)} previews')
    if nav[2].button('Next',disabled=len(rows)<=24):
        last=visible[-1];cursors.append((str(last['received_at']),str(last['id'])));st.rerun()
    from wall_preview_analytics_ui import details as analytics_details
    analytics_details(filters)
    if event and event.get('nonce')!=st.session_state.get('wall-preview-event'):
        st.session_state['wall-preview-event']=event.get('nonce')
        if event.get('id') in {str(r['id']) for r in visible}:
            if event.get('action')=='delete':st.session_state['wall-preview-delete']=event['id']
            _viewer(user,event['id'],event.get('action','view'))
