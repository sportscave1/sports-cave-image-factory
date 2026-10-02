"""Small independent fragments; polling cannot send or mutate the composer."""
from html import escape
import uuid
import streamlit as st
from crm_campaign_progress import load_progress, expire, polling_seconds, POLL_SECONDS
from crm_store import StoreUnavailable


def poll(key, seconds):
    """One native fragment event; stop automatically when its region unmounts."""
    with st.container(key=key): clicked=st.button('Update status', key=key+'_tick')
    # Scoped selectors/timers, no broad dialog mutation or component messaging.
    st.html('<style>.st-key-'+key+'{display:none}</style><script>/* '+uuid.uuid4().hex+' */'+
        '(()=>{const key='+repr(key)+';window.scCampaignTimers??={};'+
        'clearTimeout(window.scCampaignTimers[key]);const tick=()=>{'+
        'const b=document.querySelector(".st-key-"+key+" button");if(!b||!b.isConnected)return;'+
        'const dialog=document.querySelector("[role=dialog]");'+
        'if(dialog&&(key==="crm-send-tray-poll"||(key==="crm-history-poll"&&!dialog.querySelector(".st-key-crm-send-progress,.st-key-crm-send-review-summary")))){'+
        'window.scCampaignTimers[key]=setTimeout(tick,3000);return;}'+
        'b.click();'+
        '};window.scCampaignTimers[key]=setTimeout(tick,'+str(int(seconds*1000))+');})();</script>', unsafe_allow_javascript=True)
    return clicked


def dismiss():
    st.session_state.pop('campaign_send_dialog_id', None)


def _analytics(identity):
    dismiss()
    from crm_campaign_home import return_home
    return_home()
    st.session_state.pop('campaign_show_drafts',None)
    st.session_state['sent_analytics_id'] = identity
    st.session_state['campaign_history_view'] = 'Sent'
    st.rerun()


def status_content(store, identity, *, actions=True):
    st.html('''<style>[role="dialog"]:has(.st-key-crm-send-progress){max-width:520px;width:calc(100vw - 32px)}
      [role="dialog"]:has(.st-key-crm-send-progress)>div:first-child{display:none!important}
      [role="dialog"]:has(.st-key-crm-send-progress) .st-key-crm-review-actions,
      [role="dialog"]:has(.st-key-crm-send-progress) .st-key-crm-review-dismiss{display:none}
      .st-key-crm-send-progress [data-testid="stVerticalBlock"]{gap:6px}
      .st-key-crm-send-progress p{margin-bottom:2px}</style>''')
    try:
        rows = load_progress(store, st.session_state, [identity])
        row = rows.get(identity)
    except StoreUnavailable:
        st.caption('Status temporarily unavailable · background delivery continues.')
        row = None
    with st.container(key='crm-send-progress'):
        if row:
            st.markdown('### '+row['title'])
            st.text(row['name'])
            st.progress(row['percent'])
            st.caption(str(row['processed'])+' / '+str(row['total'])+' processed')
            st.caption(str(row['submitted'])+' submitted · '+str(row['skipped'])+' skipped · '+
                       str(row['failed'])+' failed · '+str(row['held'])+' held')
            if row['held']: st.caption('⚠ Submission uncertain · needs attention. Do not resend.')
            elif row['failed']: st.caption('⚠ Some submissions failed. Review delivery history before retrying.')
            elif row['complete']: st.caption('✓ Processing complete · submitted does not mean delivered.')
            elif row['status']=='SCHEDULED': st.caption('Queued securely · delivery starts at the scheduled time.')
            elif row['status'] in ('PAUSED','CANCELLED'): st.caption('Delivery '+row['status'].lower()+'.')
            elif row['processed']==row['total'] and row['total']: st.caption('Awaiting worker completion.')
        else: st.caption('Waiting for campaign status…')
        if actions:
            with st.container(horizontal=True, key='crm-send-progress-actions'):
                if st.button('Done' if row and row['complete'] else 'Minimise', key='send_progress_minimise'):
                    dismiss(); st.rerun()
                if row and row['complete'] and st.button('View analytics', key='send_progress_analytics'):
                    _analytics(identity)
                if st.button('Close', key='send_progress_close'):
                    st.session_state.get('campaign_send_progress', {}).pop(identity, None)
                    dismiss(); st.rerun()
        if not row or (not row['complete'] and row['status'] not in ('PAUSED','CANCELLED')):
            poll('crm-send-progress-poll', polling_seconds(row) if row else POLL_SECONDS)
    return row


@st.dialog('Campaign status', width='small', on_dismiss=dismiss)
def progress_dialog(store, identity):
    status_content(store, identity)


@st.fragment
def status_tray(store):
    tracked = st.session_state.get('campaign_send_progress', {})
    if not tracked: return
    try:
        rows = load_progress(store, st.session_state, tracked)
        expire(st.session_state, rows)
    except StoreUnavailable:
        rows = {}
    if not tracked: return
    # Fixed overlay: no page height or reserved block; bounded even with many sends.
    st.html('''<style>.st-key-crm-send-tray{position:fixed;right:18px;bottom:18px;width:min(340px,calc(100vw - 36px));
      z-index:80;background:#fffdf8;border:1px solid #ddd5c3;padding:8px 12px;box-shadow:0 2px 12px #0001;max-height:180px;overflow:auto}
      .st-key-crm-send-tray [data-testid="stVerticalBlock"]{gap:3px}
      .st-key-crm-send-tray p{margin:0;font-size:12px}</style>''')
    with st.container(key='crm-send-tray'):
        if len(tracked)>1: st.caption(str(len(tracked))+' campaign statuses')
        for identity,item in list(tracked.items()):
            row = rows.get(identity)
            label = ('✓ Sent' if row['complete'] and not row['attention'] else '⚠ Needs attention' if row['attention'] else row['status'].title()) if row else 'Status unavailable'
            st.html('<div style="font-size:12px;overflow-wrap:anywhere">'+escape(label+' · '+item['name'])+
                    (' · '+str(row['processed'])+'/'+str(row['total']) if row else '')+'</div>')
            with st.container(horizontal=True):
                if st.button('Open',key='send_tray_open_'+identity):
                    st.session_state['campaign_send_dialog_id']=identity
                    st.session_state.pop('campaign_progress_cache',None)
                    progress_dialog(store,identity)
                if st.button('×',help='Hide status; background delivery continues',key='send_tray_hide_'+identity):
                    tracked.pop(identity,None); st.rerun(scope='fragment')
        # A dialog owns its own status fragment; don't remount it from this timer.
        # Browser polling defers while any modal is actually mounted. Keeping
        # this timer also recovers after an unexpected full app/session rerun;
        # an old visibility hint must never strand the tray without refresh.
        if poll('crm-send-tray-poll', min((polling_seconds(r) for r in rows.values()),default=POLL_SECONDS)):
            dismiss()
            expire(st.session_state,rows)
            if not tracked:st.rerun(scope='fragment')


def operational_view(store,user,delivery):
    """Explicit history View only; no automatic post-queue authoring lock screen."""
    operational_status(store,str(delivery['id']))
    with st.container(horizontal=True):
        if st.button('Back to campaigns',key='operational_back'):
            from crm_campaign_home import return_home
            return_home();st.rerun()
        if st.button('Duplicate',key='operational_duplicate'):
            from crm_campaign_page import open_editor
            open_editor(store.duplicate(user,delivery['id']));st.rerun()
    if st.button('Email preview',key='operational_preview'):
        snapshot=store.template(delivery['template_id'],delivery['template_version'])
        if snapshot.get('document'):
            from crm_preview_cache import preview
            st.iframe(preview(st.session_state,snapshot['document'],snapshot['render_settings'])['html'],height=220)


@st.fragment
def operational_status(store,identity):
    row=status_content(store,identity,actions=False)
    if row and row['complete'] and st.button('View analytics',key='operational_analytics'):
        _analytics(identity)
