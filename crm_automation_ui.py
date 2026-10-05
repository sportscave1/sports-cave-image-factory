"""Automations: the existing email Home and composer with trigger/flow controls."""
from copy import deepcopy
import uuid
import streamlit as st
from crm_automation_definition import TRIGGERS,MARKETS,email_step,status
from crm_automation_store import AutomationStore
from crm_automation_read_cache import job
from crm_store import StoreUnavailable

def home_state():return st.session_state.setdefault('automation_home_state',{})


def changed():
    # Definitions/counts/table change; delivery/order summaries retain last-good values.
    state=home_state();cache=state.get('campaign_home_cache',{})
    state.pop('automation_identity_cache',None)
    state['publication_checked']=0
    for group in ('counts','table','identities','publication'):
        state.get('activity',{}).pop(group,None)
    for identity in list(cache):
        if identity[1][0] in ('counts','table','identities','publication'):
            cache.pop(identity)
            state.get('automation_read_terminal',{}).pop(identity,None)
            state.get('automation_read_started',{}).pop(identity,None)


def open_flow(identity):
    st.session_state['automation_selected']=str(identity)
    st.session_state.pop('automation_editor',None);st.query_params['automation']=str(identity)
    st.rerun()


@st.dialog('Create automation',width='small')
def chooser(store,user):
    st.caption('Choose a trigger. Publishing listens for future events only.')
    for kind,(name,label,_) in TRIGGERS.items():
        if st.button(name+' · '+label,key='auto_create_'+kind,use_container_width=True):
            row=store.create(user,kind);changed();open_flow(row['id'])
    with st.expander('Start from scratch'):
        kind=st.selectbox('Choose trigger',list(TRIGGERS),format_func=lambda t:TRIGGERS[t][1],key='auto_scratch_trigger')
        if st.button('Create blank flow',key='auto_scratch_create'):
            row=store.create(user,kind,'New automation');changed();open_flow(row['id'])
    st.caption('Product viewed · Product added to cart · Cart viewed · Checkout started: coming / secure identity-dependent. Anonymous activity never sends email.')


@st.dialog('Delete automation?',width='small')
def delete_dialog(store,user,row):
    st.write(row['name']);st.caption('Remove from Automations. Send and journey history is retained.')
    cancel,delete=st.columns(2)
    if cancel.button('Cancel',use_container_width=True):st.rerun()
    if delete.button('Delete',type='primary',use_container_width=True):
        store.lifecycle(user,row['id'],'delete');changed();st.rerun()


@st.fragment
def home(store,user,shop=None):
    from crm_automation_home import home as render_home
    render_home(shop,store,user)


def flow_email_control(flow,identity,selected):
    from crm_campaign_recovery import flush_current
    selection=st.selectbox('Flow email',list(range(len(flow['emails']))),index=next(i for i,s in enumerate(flow['emails']) if s['step_id']==selected),format_func=lambda i:'Email '+str(i+1)+' · '+(flow['emails'][i]['document']['content']['subject'] or 'Untitled')+' · '+str(flow['emails'][i]['delay_seconds']//60)+' min delay',key='auto_flow_step_'+str(identity)+'_'+str(len(flow['emails'])))
    if flow['emails'][selection]['step_id']!=selected:
        if not flush_current():return
        st.session_state['automation_step']=flow['emails'][selection]['step_id']
        st.session_state.pop('automation_editor',None);st.rerun()


def add_email_controls(store,user,editor,key):
    from crm_campaign_recovery import flush_current
    if st.button('Duplicate email',key=key+'duplicate_step'):
        if not flush_current(force=True):return
        fresh=store.flow(editor['id']);definition=deepcopy(fresh['config']['draft'])
        index=next(i for i,s in enumerate(definition['emails']) if s['step_id']==store.step_id)
        source=definition['emails'][index]
        definition['emails'].insert(index+1,email_step(source['document'],source['delay_seconds']))
        store.save_flow(user,editor['id'],fresh['name'],definition,fresh['config']['revision']);changed()
        st.session_state['automation_step']=definition['emails'][index+1]['step_id'];st.session_state.pop('automation_editor',None);st.rerun()
    add,blank=st.columns(2)
    for column,label,duplicate in ((add,'+ Add email · duplicate previous',True),(blank,'+ Add email · start blank',False)):
        if column.button(label,key=key+str(duplicate)):
            if not flush_current(force=True):return
            current=store.flow(editor['id']);new=deepcopy(current['config']['draft'])
            new['emails'].append(email_step(new['emails'][-1]['document'] if duplicate else None,86400))
            saved=store.save_flow(user,editor['id'],editor['name'],new,current['config']['revision'])
            st.session_state['automation_step']=saved['config']['draft']['emails'][-1]['step_id']
            st.session_state.pop('automation_editor',None);changed();st.rerun()


def settings_control(editor,key):
    context=st.session_state['automation_editor_context'];store,user=context
    row=store.flow(editor['id']);flow=deepcopy(row['config']['draft']);step=next(s for s in flow['emails'] if s['step_id']==store.step_id)
    flow_email_control(flow,editor['id'],store.step_id)
    kind=st.selectbox('Trigger',list(TRIGGERS),index=list(TRIGGERS).index(flow['trigger']),format_func=lambda t:TRIGGERS[t][1],key=key+'trigger')
    rules=[]
    from crm_automation_definition import RULE_FIELDS
    for index,rule in enumerate(flow['rules']):
        field,condition,value,remove=st.columns([1,1,1,0.6])
        selected_field=field.selectbox('Field',list(RULE_FIELDS),index=list(RULE_FIELDS).index(rule['field']),format_func=lambda f:RULE_FIELDS[f],key=key+'rule_field_'+str(index))
        operation='at_least' if selected_field=='order_value' else 'is'
        condition.selectbox('Condition',[operation],key=key+'rule_condition_'+str(index)+selected_field)
        if selected_field=='market':
            market=value.selectbox('Value',MARKETS[1:],index=MARKETS[1:].index(rule['value']) if rule['value'] in MARKETS[1:] else 0,key=key+'rule_value_'+str(index)+'market')
        else:
            initial=rule['value'] if rule['field']==selected_field else ('AU' if selected_field in ('customer_country','checkout_country') else 'AUD 100' if selected_field=='order_value' else '')
            market=value.text_input('Value',value=initial,max_chars=150,key=key+'rule_value_'+str(index)+selected_field)
            if selected_field in ('customer_country','checkout_country'):market=market.upper()
        if not remove.button('Remove',icon=':material/close:',key=key+'rule_remove_'+str(index)):
            rules.append({'field':selected_field,'condition':operation,'value':market})
    if len(rules)<12 and st.button('+ Add rule',key=key+'add_rule'):
        rules.append({'field':'market','condition':'is','value':'AU'})
    st.caption('Rules use AND. Consent and trigger exit checks are always required.')
    days=st.selectbox('Re-entry',[0,7,30,90],index=[0,7,30,90].index(flow['reentry_days']),format_func=lambda d:'Once ever' if d==0 else 'After '+str(d)+' days',key=key+'reentry')
    delay=st.number_input('Delay before email (minutes)',min_value=0,max_value=525600,value=step['delay_seconds']//60,step=1,key=key+'delay')
    st.caption('Flow status · '+status(row)+' · fresh consent and suppressions checked before every email')
    desired=deepcopy(flow);desired.update(trigger=kind,rules=rules,reentry_days=days)
    store.preview_trigger=kind
    if kind=='abandoned':
        minutes=st.number_input('Qualify as abandoned after inactivity (minutes)',min_value=1,max_value=10080,value=flow.get('abandonment_seconds',3600)//60,key=key+'abandonment')
        desired['abandonment_seconds']=int(minutes)*60
        st.caption('Qualification timer starts after the last signed checkout update. Email delay starts after qualification.')
    next(s for s in desired['emails'] if s['step_id']==store.step_id)['delay_seconds']=step['delay_seconds'] if int(delay)==step['delay_seconds']//60 else int(delay)*60
    if desired!=flow:
        from crm_automation_definition import validate
        try:validate(desired)
        except ValueError as exc:st.caption(str(exc));return
        # Include current content in the same optimistic write.
        next(s for s in desired['emails'] if s['step_id']==store.step_id)['document']=deepcopy(editor['document'])
        updated=store.save_flow(user,row['id'],editor['name'],desired,editor['version'])
        editor['version']=updated['config']['revision']
    add_email_controls(store,user,editor,key)


def detail(shop,store,actions,identity):
    store.preview_shop=shop
    from crm_campaign_page import composer_form
    from crm_campaign_send_ui import test_control,safe_error
    from crm_campaign_recovery import flush_current
    from crm_html_workspace import html_document,composer_styles
    user=actions.user;row=store.flow(identity);flow=row['config']['draft'];readonly=status(row)=='ARCHIVED'
    publication=row['config'].get('publication') or {}
    if publication.get('state')=='FAILED':st.error(publication.get('error') or 'Publication failed. Review the saved draft and retry.')
    if publication.get('state')=='PUBLISHING':st.caption('Publishing saved revision '+str(publication['revision'])+' · you can continue editing the next draft.')
    if st.button('← Automations',key='auto_back'):
        if flush_current():
            st.session_state.pop('_automation_preview_open',None)
            st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None);st.rerun()
    title,action=st.columns([3,1]);title.subheader(row['name']);title.caption(status(row)+' · Published version '+str(row['config']['published_version']))
    if row['status']=='ACTIVE' and not readonly:
        if action.button('Pause'):store.lifecycle(user,identity,'pause');changed();st.rerun()
    elif row['status']=='PAUSED' and not readonly:
        if action.button('Resume'):store.lifecycle(user,identity,'resume');changed();st.rerun()
    selected=st.session_state.get('automation_step')
    if selected not in [s['step_id'] for s in flow['emails']]:selected=flow['emails'][0]['step_id']
    step=next(s for s in flow['emails'] if s['step_id']==selected)
    if store.step_id!=step['step_id']:store.step_id=step['step_id']
    editor=st.session_state.get('automation_editor')
    if editor and (str(editor['id'])!=str(identity) or st.session_state.get('automation_step')!=step['step_id']):
        if not flush_current():return
        editor=None;row=store.flow(identity);flow=row['config']['draft']
    if editor is None:
        editor=store.draft(identity);editor['document']=html_document(editor['document'])
        st.session_state['automation_editor']=editor;st.session_state['automation_saved']=deepcopy(editor)
    st.session_state['automation_step']=step['step_id'];st.session_state['automation_editor_context']=(store,user)
    store.preview_trigger=flow['trigger']
    key='auto_'+str(identity)+'_'+step['step_id']+'_'
    namespace=getattr(shop,'namespace',None)
    preview_scope=(key,flow['trigger'],namespace if isinstance(namespace,str) else 'configured-shop')
    if st.session_state.get('_automation_preview_open')!=preview_scope:
        st.session_state['_automation_preview_open']=preview_scope
        st.session_state.pop('_automation_checkout_pin',None)
        from crm_checkout_preview import needs_checkout
        if needs_checkout(editor['document']):
            from crm_abandoned_checkout import preview_context
            preview_context(st.session_state,shop,auto_refresh=False,slot='_automation_checkout_pin')
    cfg=store.render_settings();composer_styles()
    st.html('''<style>
    .st-key-crm-automation-editor [data-testid="stVerticalBlock"]{gap:8px}
    .st-key-crm-automation-editor h3{margin:0;padding:0;font-size:20px}
    .st-key-crm-automation-editor .st-key-crm-composer-preview{padding:12px;gap:6px}
    .st-key-crm-automation-editor .st-key-crm-composer-preview iframe{height:clamp(340px,calc(100dvh - var(--sc-topbar-height,64px) - 205px),680px)!important}
    .st-key-crm-automation-editor button[kind="primary"]{background:#c8a346!important;border-color:#b99436!important;color:#141414!important}
    @media(max-width:760px){
    .st-key-crm-automation-editor .st-key-crm-composer-layout{flex-wrap:wrap!important}
    .st-key-crm-automation-editor .st-key-crm-composer-layout>div:has(>.st-key-crm-composer-controls){width:100%!important;flex-basis:100%!important}
    .st-key-crm-automation-editor .st-key-crm-composer-controls{width:100%!important;min-width:0!important;height:auto!important;max-height:none!important;overflow:visible!important}
    .st-key-crm-automation-editor .st-key-crm-composer-layout>div:has(>.st-key-crm-composer-preview){width:100%!important;flex-basis:100%!important;min-width:0!important}
    .st-key-crm-automation-editor .st-key-crm-composer-preview{width:100%!important;max-width:100%!important;box-sizing:border-box!important}
    }
    </style>''')
    if readonly:
        from crm_html_workspace import composer_canvas
        with st.container(horizontal=True,gap='small'):
            with st.container(width=360):flow_email_control(flow,identity,selected)
            with st.container(width='stretch'):composer_canvas(editor['document'],cfg,key,store)
        return
    with st.container(horizontal=True,vertical_alignment='center'):
        if st.button('Save draft',key=key+'save'):
            if flush_current(force=True):changed();st.toast('Draft saved')
        test_control(store,user,editor,key,cfg=cfg)
        publish_requested=st.button('Publish now',type='primary',disabled=publication.get('state')=='PUBLISHING',key=key+'publish')
    composer_form(shop,store,actions,editor,key,cfg,None,True,mode='automation',settings_control=settings_control)
    from pathlib import Path
    publish_js=Path(__file__).with_name('components').joinpath('crm_sections','automation_publish.js').read_text(encoding='utf-8')
    st.html('<script>'+publish_js+'</script>',unsafe_allow_javascript=True)
    if publish_requested:
        try:
            if not flush_current(force=True):return
            job=store.request_publish(user,identity,editor['version'])
            # Prime last-good table rows so the accepted state is visible before
            # the bounded table refresh completes. KPI values stay untouched.
            from crm_automation_home import accepted_publication
            accepted_publication(job);changed()
            st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None)
            st.session_state['automation_notice']='Publication accepted · validation continues in the background';st.rerun()
        except (ValueError,StoreUnavailable,PermissionError) as exc:
            st.error('Automation storage is temporarily unavailable. Your draft is retained; retry publishing.' if isinstance(exc,StoreUnavailable) else safe_error(exc))
    st.session_state[key+'editor_emitted']=True
    if st.toggle('Show email step analytics',key='auto_step_stats'):
        from crm_automation_home_data import step_metrics
        names={s['step_id']:'Email '+str(i+1)+' · '+s['document']['content']['subject'] for i,s in enumerate(flow['emails'])}
        st.dataframe([{'Email':names.get(r['step_id'],'Previous version email'),**{k.title():v for k,v in r.items() if k!='step_id'}} for r in step_metrics(store,identity)],hide_index=True,use_container_width=True)


def workspace(shop,base,actions,navigate=lambda _:None):
    if st.session_state.get('email_editor_mode')!='automation':
        st.session_state.pop('_automation_preview_open',None)
    st.session_state['email_editor_mode']='automation'
    store=AutomationStore(base.connect);identity=st.session_state.get('automation_selected') or st.query_params.get('automation')
    notice=st.session_state.pop('automation_notice',None)
    if notice:st.toast(notice,icon=':material/check_circle:')
    try:
        target=st.session_state.get('automation_requested_route')
        if target:
            from crm_campaign_recovery import flush_current
            st.warning('Save your automation changes before leaving.')
            save,stay=st.columns(2)
            if save.button('Save and leave') and flush_current(force=True):
                st.session_state.pop('automation_requested_route',None);navigate(target);st.rerun()
            if stay.button('Keep editing'):st.session_state.pop('automation_requested_route',None);st.rerun()
        if identity:
            from crm_automation_definition import native
            existing=store.get('automations',str(uuid.UUID(str(identity))))
            if existing and not native(existing):
                st.subheader(existing['name']);st.caption('Legacy '+existing['status'].lower()+' flow · runtime and audit history retained')
                if st.button('← Automations',key='legacy_auto_back'):
                    st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None);st.rerun()
                if existing['status']=='DRAFT' and existing['trigger_type'] in TRIGGERS and st.button('Convert draft to shared editor'):
                    store.adopt(actions.user,identity);changed();st.rerun()
                if existing['status']=='ACTIVE' and st.button('Pause legacy flow'):
                    store.lifecycle(actions.user,identity,'pause');changed();st.rerun()
            else:
                with st.container(key='crm-automation-editor'):
                    detail(shop,store,actions,identity)
        else:
            st.session_state.pop('_automation_preview_open',None)
            home(store,actions.user,shop=shop)
    except (StoreUnavailable,ValueError,PermissionError) as exc:st.warning(str(exc))
