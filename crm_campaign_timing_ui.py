"""Shared schedule dialogs for Home and detail; durable backend owns mutations."""
import uuid
from copy import deepcopy
from datetime import datetime
import streamlit as st
_UNREAD=object()


def refresh_timing(identity):
    st.session_state.pop('campaign_progress_cache',None)
    st.session_state.get('campaign_home_progress',{}).pop(str(identity),None)
    # Invalidate list projections without discarding the user's filters.
    cache=st.session_state.get('campaign_home_cache',{})
    for key in list(cache):
        if key[1][0] in ('table','progress','counts'):cache.pop(key,None)


def close_home_actions():
    # Streamlit keeps a popover open when its button opens a dialog. Dismiss
    # only Campaign Home actions so its portal cannot cover modal controls.
    st.html("""<script>(()=>{
      for(const node of document.querySelectorAll('.st-key-crm-home-table [data-testid="stPopover"] button[aria-expanded="true"]'))node.click();
    })();</script>""",unsafe_allow_javascript=True)


@st.dialog('Edit campaign schedule')
def edit_schedule(store,user,delivery):
    close_home_actions()
    from crm_navigation import require
    require(user,'crm_campaigns_manage')
    identity=str(delivery['id']);prefix='schedule-edit-'+identity
    context_key=prefix+'-context'
    if context_key not in st.session_state:
        prior=store.state('campaign-timing:'+identity) or {}
        context=store.q("SELECT d.document->>'market' AS market,d.document->'send_timing' AS timing FROM crm_campaign_drafts d WHERE d.id=%s",(identity,),one=True)
        st.session_state[context_key]=(prior,context)
    prior,context=st.session_state[context_key]
    # Capture revision on first open, never silently refresh it on Save.
    revision=st.session_state.setdefault(prefix+'-revision',prior.get('operation_id'))
    timing=prior.get('timing') or context['timing']
    from crm_campaign_schedule import summary
    st.caption('Current timing: '+summary(timing))
    doc={'market':context['market'],'send_timing':deepcopy(timing)}
    if timing.get('time_basis')=='recipient_local' or 'policy_version' not in timing:
        if 'policy_version' not in timing:st.caption('Uses the original reviewed recipient timezones. Location corrections require a separate review.')
        st.caption('Recipient local time')
        st.caption('Each recipient receives this campaign at the selected time in their own timezone.')
        day_col,time_col=st.columns(2)
        day=day_col.date_input('Date',datetime.strptime(timing['date'],'%Y-%m-%d').date(),key=prefix+'-date')
        hour=time_col.time_input('Time',datetime.strptime(timing['time'],'%H:%M').time(),key=prefix+'-time',step=60)
        doc['send_timing']={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':day.isoformat(),'time':hour.strftime('%H:%M')}
    else:
        # Preserve the existing V7 explicit-timezone authoring contract.
        from crm_campaign_controls import timing_control
        timing_control(doc,prefix,schedule_only=True)
    from crm_campaign_progress import load_progress
    from crm_campaign_countdown import local_markup,arm
    row=load_progress(store,st.session_state,[identity]).get(identity,{})
    if row.get('next_due_at'):st.html(local_markup(row['next_due_at']));arm()
    cancel,save=st.columns(2)
    if cancel.button('Cancel',key=prefix+'-cancel'):
        st.session_state.pop(prefix+'-revision',None);st.rerun()
    if save.button('Save schedule',type='primary',key=prefix+'-save'):
        proposed=doc['send_timing']
        operation=st.session_state.setdefault(prefix+'-operations',{}).setdefault(str(proposed),str(uuid.uuid4()))
        try:
            from crm_campaign_schedule import change_pending
            change_pending(store,user,identity,proposed,operation,confirmed=True,expected_operation_id=revision)
        except (ValueError,PermissionError,RuntimeError) as exc:st.error(str(exc));return
        refresh_timing(identity);st.session_state.pop(prefix+'-revision',None)
        st.session_state['campaign_home_notice']='Schedule updated'
        st.rerun()


@st.dialog('Send this campaign now?')
def send_now(store,user,delivery):
    close_home_actions()
    from crm_navigation import require
    require(user,'crm_campaigns_manage')
    identity=str(delivery['id']);prefix='schedule-now-'+identity
    context_key=prefix+'-context'
    if context_key not in st.session_state:st.session_state[context_key]=store.state('campaign-timing:'+identity) or {}
    prior=st.session_state[context_key]
    revision=st.session_state.setdefault(prefix+'-revision',prior.get('operation_id'))
    st.write(delivery.get('name','Campaign'))
    st.caption("This will start sending to the campaign's eligible queued recipients instead of waiting for the scheduled time.")
    cancel,confirm=st.columns(2)
    if cancel.button('Cancel',key=prefix+'-cancel'):
        st.session_state.pop(prefix+'-revision',None);st.rerun()
    if confirm.button('Confirm Send Now',type='primary',key=prefix+'-confirm'):
        operation=st.session_state.setdefault(prefix+'-operation',str(uuid.uuid4()))
        try:
            from crm_campaign_schedule import change_pending
            change_pending(store,user,identity,{'mode':'now'},operation,confirmed=True,expected_operation_id=revision)
        except (ValueError,PermissionError,RuntimeError) as exc:st.error(str(exc));return
        refresh_timing(identity);st.session_state.pop(prefix+'-revision',None)
        from crm_campaign_home import return_home
        return_home();st.session_state['campaign_home_notice']='Campaign queued for sending';st.rerun()


def pending_controls(store,user,delivery,*,progress=_UNREAD):
    if delivery.get('status')!='SCHEDULED':return
    from crm_navigation import require
    require(user,'crm_campaigns_manage')
    prefix='campaign-timing-'+str(delivery['id'])
    from crm_campaign_progress import load_progress
    if progress is _UNREAD:progress=load_progress(store,st.session_state,[str(delivery['id'])]).get(str(delivery['id']))
    locked=not progress or progress.get('started') or progress.get('attention')
    if locked:st.caption('Schedule changes are unavailable after processing begins or when delivery needs attention.')
    edit=send=st
    if edit.button('Edit schedule',key=prefix+'-edit',disabled=bool(locked)):open_edit_schedule(store,user,delivery)
    if send.button('Send now',key=prefix+'-now',disabled=bool(locked)):open_send_now(store,user,delivery)


def open_edit_schedule(store,user,delivery):
    prefix='schedule-edit-'+str(delivery['id'])
    for suffix in ('revision','operations','date','time','context'):st.session_state.pop(prefix+'-'+suffix,None)
    edit_schedule(store,user,delivery)


def open_send_now(store,user,delivery):
    prefix='schedule-now-'+str(delivery['id'])
    for suffix in ('revision','operation','context'):st.session_state.pop(prefix+'-'+suffix,None)
    send_now(store,user,delivery)
