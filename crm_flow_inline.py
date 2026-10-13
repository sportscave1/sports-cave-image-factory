"""Small native flow controls. Publication remains flow-level authority."""
from copy import deepcopy
import streamlit as st
from crm_automation_definition import status
from crm_automation_timing import delay_controls
from crm_store import StoreUnavailable


def step_state(row,step):
    """Only a persisted publication can be LIVE; draft enabled is not live."""
    published=bool(row['config'].get('published_version') and any(
        s.get('step_id')==step['step_id'] and s.get('enabled',True) for s in row.get('steps',[])))
    if published and status(row)=='ACTIVE':return 'LIVE'
    if published and status(row)=='PAUSED':return 'PAUSED'
    return 'DRAFT'


def status_options(row,step):
    options=[step_state(row,step)]
    if status(row)=='ARCHIVED':return options
    options.append('Disable in draft' if step.get('enabled',True) else 'Enable in draft')
    busy=row['config'].get('publication',{}).get('state')=='PUBLISHING'
    if row['status']=='ACTIVE':options.append('Pause flow')
    if not busy:
        if row['status']=='PAUSED' and row['config'].get('published_version'):options.append('Resume flow')
        options.append('Publish flow')
    return options


def status_action(store,user,row,step,key):
    action=st.session_state[key]
    # Consume the event before persistence. Failures never replay on rerender.
    st.session_state[key]=step_state(row,step)
    if action not in status_options(row,step)[1:]:return
    try:
        from crm_campaign_recovery import flush_current
        from crm_automation_ui import changed
        if not flush_current(force=True):return
        fresh=store.flow(row['id'])
        if fresh['config']['draft']!=row['config']['draft'] or fresh['status']!=row['status']:
            raise ValueError('The flow changed. Review its current state and retry.')
        if action in ('Disable in draft','Enable in draft'):
            draft=deepcopy(fresh['config']['draft'])
            target=next(s for s in draft['emails'] if s['step_id']==step['step_id'])
            target['enabled']=action=='Enable in draft'
            store.save_flow(user,row['id'],fresh['name'],draft,fresh['config']['revision'])
        elif action=='Publish flow':
            if fresh['trigger_type']=='abandoned':
                job=store.request_publish(user,row['id'],fresh['config']['revision'])
                if not job.get('unchanged'):
                    from crm_automation_home import accepted_publication
                    accepted_publication(job)
            else:
                st.session_state['automation-confirm-publication']=(str(row['id']),fresh['config']['revision'])
        else:store.lifecycle(user,row['id'],'pause' if action=='Pause flow' else 'resume')
        changed();st.session_state['flow-toolbar-dirty']=True
    except (ValueError,PermissionError,StoreUnavailable) as exc:
        st.session_state['flow-inline-error']=str(exc)


def status_control(store,user,row,step):
    state=step_state(row,step)
    key='flow-status-'+step['step_id']
    st.session_state[key]=state
    with st.container(key='flow-state-'+state.lower()+'-'+step['step_id']):
        st.selectbox('Status and actions for '+(step.get('name') or 'email'),status_options(row,step),
            key=key,label_visibility='collapsed',disabled=status(row)=='ARCHIVED',
            help='Status refers to the published email. Publish, Pause and Resume affect the whole flow; draft changes do not alter the live version.',
            on_change=status_action,args=(store,user,row,step,key))


@st.dialog('Delete email?',width='small')
def delete_email(store,user,row,step):
    st.write('Remove '+(step.get('name') or 'this email')+' from the draft? Published emails and delivery history are retained.')
    cancel,confirm=st.columns(2)
    if cancel.button('Cancel',key='flow-delete-cancel'):st.rerun(scope='app')
    if confirm.button('Delete email',key='flow-delete-confirm',type='primary'):
        from crm_flow_builder import edit_sequence,save
        try:
            draft=edit_sequence(row['config']['draft'],step['step_id'],'delete')
            if save(store,user,row,draft,rerun=False) is False:return
            st.rerun(scope='app')
        except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))


def controls(store,user,row,step,index):
    from crm_flow_page import open_email
    flow=row['config']['draft'];sid=step['step_id'];prefix='flow-step-'+sid+'-'
    readonly=status(row)=='ARCHIVED'
    amount,unit=delay_controls(step['delay_seconds'])
    amount_key=prefix+'delay';unit_key=prefix+'unit'
    snapshot_key=prefix+'saved-delay'
    if st.session_state.get(snapshot_key)!=step['delay_seconds']:
        st.session_state[amount_key]=amount;st.session_state[unit_key]=unit
        st.session_state[snapshot_key]=step['delay_seconds']
    with st.container(horizontal=True,vertical_alignment='center',key='flow-inline-'+sid,gap='small'):
        if st.button('Edit Email',icon=':material/edit:',help='Edit email',key=prefix+'edit'):open_email(sid)
        with st.container(width=66):
            delay=st.number_input('Delay for email '+str(index+1),min_value=0,max_value=525600,value=amount,
                step=1,key=amount_key,label_visibility='collapsed',disabled=readonly,
                on_change=save_delay,args=(store,user,row,step,amount_key,unit_key))
        with st.container(width=92):
            units=st.selectbox('Delay unit for email '+str(index+1),['Minutes','Hours','Days'],index=['Minutes','Hours','Days'].index(unit),
                key=unit_key,label_visibility='collapsed',disabled=readonly,
                on_change=save_delay,args=(store,user,row,step,amount_key,unit_key))
        for label,action,icon,disabled in [('Move up','up','arrow_upward',index==0),('Move down','down','arrow_downward',index==len(flow['emails'])-1)]:
            st.button(label,icon=':material/'+icon+':',help=label,key=prefix+action,disabled=readonly or disabled,
                on_click=move_email,args=(store,user,row,sid,action))
        if st.button('Delete email',icon=':material/delete:',help='Delete email' if len(flow['emails'])>1 else 'Keep at least one email in this draft',
                key=prefix+'delete',disabled=readonly or len(flow['emails'])==1):delete_email(store,user,row,step)


def move_email(store,user,row,sid,action):
    from crm_flow_builder import edit_sequence,save
    try:
        fresh=store.flow(row['id'])
        if fresh['config']['draft']!=row['config']['draft']:
            raise ValueError('The sequence changed. Review it and retry.')
        draft=edit_sequence(fresh['config']['draft'],sid,action)
        if save(store,user,fresh,draft,rerun=False) is False:return
        st.session_state['flow-toolbar-dirty']=True
    except (ValueError,PermissionError,StoreUnavailable) as exc:
        st.session_state['flow-inline-error']=str(exc)


def save_delay(store,user,row,step,amount_key,unit_key):
    amount,unit=delay_controls(step['delay_seconds'])
    value=st.session_state[amount_key];units=st.session_state[unit_key]
    if (value,units)==(amount,unit):return
    try:
        from crm_flow_builder import save
        fresh=store.flow(row['id'])
        draft=deepcopy(fresh['config']['draft'])
        target=next((s for s in draft['emails'] if s['step_id']==step['step_id']),None)
        seconds=int(value)*{'Minutes':60,'Hours':3600,'Days':86400}[units]
        if target is not None and target['delay_seconds']==seconds:return
        if target is None or target['delay_seconds']!=step['delay_seconds']:
            raise ValueError('This email changed. Review its saved delay and retry.')
        target['delay_seconds']=seconds
        if save(store,user,fresh,draft,rerun=False) is False:return
        st.session_state['flow-toolbar-dirty']=True
    except (ValueError,PermissionError,StoreUnavailable) as exc:
        st.session_state[amount_key]=amount;st.session_state[unit_key]=unit
        st.session_state['flow-inline-error']=str(exc)


def cancel_rename():
    st.session_state.pop('flow-rename',None)
    st.session_state.pop('flow-rename-error',None)


def save_rename(store,user,identity):
    original=st.session_state.get('flow-rename')
    if not original or str(original['id'])!=str(identity):return
    name=st.session_state.get('flow-rename-input','').strip()
    if not name or len(name)>150:
        st.session_state['flow-rename-error']='Use a name of 1-150 characters.';return
    if name==original['name']:cancel_rename();return
    try:
        store.save_flow(user,identity,name,original['config']['draft'],original['config']['revision'])
        from crm_automation_ui import changed
        changed();cancel_rename()
    except (ValueError,PermissionError,StoreUnavailable) as exc:
        st.session_state['flow-rename-error']=str(exc)


def title_control(store,user,row,title):
    from html import escape
    editing=st.session_state.get('flow-rename')
    if editing and str(editing['id'])!=str(row['id']):cancel_rename();editing=None
    with st.container(horizontal=True,vertical_alignment='center',key='flow-title',gap='small'):
        if editing:
            st.text_input('Automation name',key='flow-rename-input',max_chars=150,label_visibility='collapsed',
                on_change=save_rename,args=(store,user,row['id']))
            st.button('Cancel rename',key='flow-rename-cancel',on_click=cancel_rename)
        else:
            st.html('<div class="automation-title"><strong title="'+escape(title,quote=True)+'">'+escape(title)+'</strong></div>')
            if st.button('Rename automation',icon=':material/edit:',help='Rename automation',key='flow-rename-start',disabled=status(row)=='ARCHIVED'):
                st.session_state['flow-rename']=deepcopy(row)
                st.session_state['flow-rename-input']=row['name']
                st.rerun(scope='fragment')
    error=st.session_state.get('flow-rename-error')
    if error:st.caption(error)
    original='<span hidden data-flow-rename-original="'+escape(editing['name'],quote=True)+'"></span>' if editing else ''
    st.html(original or '<span hidden></span>')


def scripts():
    from pathlib import Path
    st.html('<span hidden data-flow-inline-script></span><script>'+Path(__file__).with_name('components').joinpath('crm_sections','flow_inline.js').read_text(encoding='utf8')+'</script>',unsafe_allow_javascript=True)
