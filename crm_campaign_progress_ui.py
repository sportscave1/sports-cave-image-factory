"""Small independent fragments; polling cannot send or mutate the composer."""
import uuid
import streamlit as st
from crm_campaign_progress import load_progress, polling_seconds, POLL_SECONDS
from crm_store import StoreUnavailable
_UNREAD=object()


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


def status_content(store, identity, row=_UNREAD):
    if row is _UNREAD:
        try:
            rows = load_progress(store, st.session_state, [identity])
            row = rows.get(identity)
        except StoreUnavailable:
            st.caption('Status temporarily unavailable · background delivery continues.')
            row = None
    with st.container(key='crm-send-progress'):
        if row:
            if row['status']=='PREPARING':
                st.markdown('**Preparing**')
                st.caption(f"{row['total']:,} reviewed recipients · awaiting final verification")
                st.caption('Sending begins only after verification. No further confirmation is needed.')
                if row.get('preparation_error'):st.caption('Verification unavailable · bounded background retry pending.')
            elif row['status']=='FAILED':
                st.markdown('**Needs attention**')
                from crm_campaign_preparation import failure_message
                st.caption(failure_message(row.get('preparation_error'))+' No recipient work was released.')
            elif row['status']=='SCHEDULED':
                st.caption(f"Scheduled · {row['total']:,} recipients")
            else:
                st.markdown('**'+('Sent with issues' if row['complete'] and row['attention'] else 'Sent' if row['complete'] else 'Queued' if not row.get('started') and not row.get('worker_started_at') else row['title'])+'**')
                if row.get('started') or row.get('worker_started_at') or row['complete']:
                    st.progress(row['percent'])
                    st.caption(f"{row['processed']:,} / {row['total']:,} recipients processed")
                    st.caption(f"{row['submitted']:,} submitted · {row['skipped']:,} skipped · {row['failed']:,} failed · {row['held']:,} held")
            if row.get('stalled'): st.caption('Send appears stalled · background status retained. Do not resend.')
            if row['held']: st.caption('⚠ Submission uncertain · needs attention. Do not resend.')
            elif row['failed']: st.caption('⚠ Some submissions failed. Review delivery history before retrying.')
            elif row['complete'] and not row['submitted']: st.caption('No emails accepted by Resend. Review the blocked or failed reasons before taking action.')
            elif row['complete']: st.caption('✓ Processing complete · submitted does not mean delivered.')
            elif row['status']=='SCHEDULED':
                from crm_campaign_schedule import summary as timing_summary
                st.caption('Scheduled · '+timing_summary(row.get('timing') or {'mode':'now'}))
                if row.get('next_due_at'):
                    from crm_campaign_countdown import markup,local_markup,arm
                    st.html(local_markup(row['next_due_at'])+'<br>'+markup(row['next_due_at'],row.get('server_now')));arm()
                if (row.get('timing') or {}).get('time_basis')!='campaign_timezone' and row.get('latest_due_at'):
                    from crm_email_diagnostics import utc
                    st.caption('Window ends · '+utc(row['latest_due_at']))
            elif row['status'] in ('PAUSED','CANCELLED'): st.caption('Delivery '+row['status'].lower()+'.')
            elif row['status']=='SENDING' and (row.get('timing') or {}).get('mode')=='schedule' and row.get('next_due_at'):
                from crm_logic import date,now
                if date(row['next_due_at'])>now():
                    from crm_campaign_countdown import markup,local_markup,arm
                    st.caption(f"{row['pending']:,} recipients waiting for their scheduled time")
                    st.html(local_markup(row['next_due_at'])+'<br>'+markup(row['next_due_at'],row.get('server_now')));arm()
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


@st.fragment
def operational_view(store,user,delivery):
    from crm_navigation import require
    require(user,'crm_campaigns_manage')
    from page_presentation import inject_compact_page
    inject_compact_page(st)
    identity=str(delivery['id'])
    try:progress=load_progress(store,st.session_state,[identity]).get(identity)
    except StoreUnavailable:
        st.caption('Status temporarily unavailable · background delivery continues.')
        progress=None
    with st.container(key='crm-campaign-operational'):
        st.html('<style>.st-key-crm-operational-header [data-testid="stElementContainer"]:has([data-testid="stHtml"]){flex:1 1 180px!important;min-width:0!important}.st-key-crm-operational-header button{white-space:nowrap;word-break:normal!important}.st-key-crm-operational-header [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important}</style>')
        with st.container(horizontal=True,vertical_alignment='center',key='crm-operational-header'):
            if st.button('← Campaigns',key='operational_back'):
                from crm_campaign_home import return_home
                return_home();st.rerun()
            from html import escape
            st.html('<div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="'+escape(delivery.get('name','Campaign'),quote=True)+'">'+escape(delivery.get('name','Campaign'))+'</div>')
            from crm_campaign_timing_ui import pending_controls
            pending_controls(store,user,delivery,progress=progress)
        row=status_content(store,identity,progress)
        if row and row['complete'] and st.button('View analytics',key='operational_analytics'):_analytics(identity)
    if delivery.get('template_id') and st.button('Email preview',key='operational_preview'):
        snapshot=store.template(delivery['template_id'],delivery['template_version'])
        if snapshot.get('document'):
            from crm_preview_cache import preview
            st.iframe(preview(st.session_state,snapshot['document'],snapshot['render_settings'])['html'],height=220)


@st.fragment
def operational_status(store,identity):
    row=status_content(store,identity)
    if row and row['complete'] and st.button('View analytics',key='operational_analytics'):
        _analytics(identity)


def admin_delivery_diagnostics(store,user,identity):
    """Retained engineering view; normal campaign pages never invoke it."""
    import os_accounts
    if not os_accounts.account_is_active(user) or not os_accounts.is_admin(user):
        raise PermissionError('Administrator access required.')
    with st.expander('Delivery diagnostics'):
        # An explicit history view; no extra reads on the composer/progress tray.
        try:
            from crm_email_diagnostics import campaign_status,worker_label,utc
            report=campaign_status(store,identity)
            if report:
                st.caption(worker_label(report.get('worker') or {}))
                timing=report.get('timing') or {}
                from crm_campaign_schedule import summary as timing_summary
                st.caption('Schedule · '+timing_summary(timing))
                for zone in report.get('zones') or []:
                    st.caption(str(zone['timezone'] or 'Unknown timezone')+' · '+str(zone['recipients'])+' recipients · '+utc(zone['due_at']))
                st.caption(str(report['accepted'])+' accepted by Resend · '+str(report['delivered'])+' delivered receipts · '+str(report['delivery_problems'])+' recipients with delivery problems')
                st.caption('Acceptance is not delivery. Missing receipts do not confirm delivery or failure.')
                st.caption('Schedule guard last checked · '+utc((report.get('schedule_health') or {}).get('checked_at')))
        except StoreUnavailable:st.caption('Delivery diagnostics temporarily unavailable.')
