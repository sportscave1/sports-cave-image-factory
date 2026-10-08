"""Small independent fragments; polling cannot send or mutate the composer."""
import uuid
import streamlit as st
from crm_campaign_progress import load_progress, polling_seconds, POLL_SECONDS
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
        'if(document.hidden||(dialog&&key==="crm-history-poll")){'+
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


def status_content(store, identity):
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
            if row.get('stalled'): st.caption('Send appears stalled · background status retained. Do not resend.')
            if row['held']: st.caption('⚠ Submission uncertain · needs attention. Do not resend.')
            elif row['failed']: st.caption('⚠ Some submissions failed. Review delivery history before retrying.')
            elif row['complete'] and not row['submitted']: st.caption('No emails accepted by Resend. Review the blocked or failed reasons before taking action.')
            elif row['complete']: st.caption('✓ Processing complete · submitted does not mean delivered.')
            elif row['status']=='SCHEDULED': st.caption('Queued securely · delivery starts at the scheduled time.')
            elif row['status'] in ('PAUSED','CANCELLED'): st.caption('Delivery '+row['status'].lower()+'.')
            elif row['processed']==row['total'] and row['total']: st.caption('Awaiting worker completion.')
            # Only system-owned reason labels are displayed, never database or
            # provider exception text (which may contain private payloads).
            reasons={'schedule_missed':'Schedule missed — reschedule requires a new review; overdue messages will not be released automatically',
                     'marketing_off_schedule':'Marketing was disabled at the scheduled time',
                     'local_suppression':'Recipient suppressed locally',
                     'provider_suppression':'Recipient suppressed by Resend',
                     'smart_sending':'Recipient excluded by the sending frequency policy',
                     'provider_rejected':'Provider rejected submission',
                     'batch_retry_exhausted':'Submission retry window exhausted',
                     'batch_stop_state_changed':'Consent or suppression changed during uncertain submission',
                     'revalidation_unavailable':'Recipient verification unavailable',
                     'interrupted_submission':'Submission interrupted'}
            codes={code for values in (row.get('failures') or {}).values() for code in (values or [])}
            for code in sorted(codes & reasons.keys()):st.caption('Reason: '+reasons[code])
        else: st.caption('Waiting for campaign status…')
        if not row or (not row['complete'] and row['status'] not in ('PAUSED','CANCELLED','FAILED')):
            poll('crm-send-progress-poll', polling_seconds(row) if row else POLL_SECONDS)
    return row


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
    row=status_content(store,identity)
    with st.expander('Delivery diagnostics'):
        # An explicit history view; no extra reads on the composer/progress tray.
        try:
            from crm_email_diagnostics import campaign_status,worker_label,utc
            report=campaign_status(store,identity)
            if report:
                st.caption(worker_label(report.get('worker') or {}))
                timing=report.get('timing') or {}
                st.caption('Schedule · '+(str(timing.get('date'))+' '+str(timing.get('time'))+' recipient local time' if timing.get('mode')=='schedule' else 'Send now'))
                for zone in report.get('zones') or []:
                    st.caption(str(zone['timezone'] or 'Unknown timezone')+' · '+str(zone['recipients'])+' recipients · '+utc(zone['due_at']))
                st.caption(str(report['accepted'])+' accepted by Resend · '+str(report['delivered'])+' delivered receipts · '+str(report['delivery_problems'])+' recipients with delivery problems')
                st.caption('Acceptance is not delivery. Missing receipts do not confirm delivery or failure.')
                st.caption('Schedule guard last checked · '+utc((report.get('schedule_health') or {}).get('checked_at')))
        except StoreUnavailable:st.caption('Delivery diagnostics temporarily unavailable.')
    if row and row['complete'] and st.button('View analytics',key='operational_analytics'):
        _analytics(identity)
