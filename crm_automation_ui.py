"""Automations: the existing email Home and composer with trigger/flow controls."""
from copy import deepcopy
from html import escape
import uuid
from time import monotonic
import streamlit as st
from crm_automation_definition import TRIGGERS,MARKETS,email_step,status
from crm_automation_store import AutomationStore
from crm_campaign_home import STYLE,kpis
from crm_campaign_home_cache import job,resolve
from crm_campaign_home_data import invalidate
from crm_store import StoreUnavailable

TABS=('All automations','Drafts','Active','Paused','Archived')


def home_state():return st.session_state.setdefault('automation_home_state',{})


def changed():
    # Definitions/counts/table change; delivery/order summaries retain last-good values.
    state=home_state();cache=state.get('campaign_home_cache',{})
    for identity in list(cache):
        if identity[1][0] in ('counts','table'):cache.pop(identity)


def open_flow(identity):
    st.session_state['automation_selected']=str(identity)
    st.session_state.pop('automation_editor',None);st.query_params['automation']=str(identity)
    st.rerun()


@st.dialog('Create automation',width='small')
def chooser(store,user):
    st.caption('Choose a trigger. Publishing listens for future events only.')
    capabilities=store.state('shopify_automation_capabilities')
    for kind,(name,label,_) in TRIGGERS.items():
        available=capabilities.get('triggers',{}).get(kind,'UNVERIFIED')
        st.caption(label+' · '+available+' · drafts can be prepared before connection')
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
def metrics(store):
    from crm_automation_home_data import counts,delivery_summary,orders_summary,reporting_window
    state=home_state();stamp=monotonic()
    if 'window' not in state or stamp-state.get('window_stamp',0)>=20:
        state['window']=reporting_window();state['window_stamp']=stamp
    window=state['window'];data={};errors=[]
    for name,load,fields in (('counts',lambda:counts(store),('all_count','drafts','active','paused','archived')),
        ('delivery',lambda:delivery_summary(store,window),('sent_emails','bounce_rate','click_rate')),
        ('attribution',lambda:orders_summary(store,window),('orders',))):
        key=(name,None);value,activity=resolve(state,store,key,job(state,store,key,load),fields=fields)
        state.setdefault('activity',{})[name]=activity
        if value:data.update(value)
        if activity=='ERROR':errors.append(name)
    st.html(kpis(data,active_note='automations'))
    if errors:st.caption('Some statistics could not refresh. Last verified values remain visible.')


@st.fragment
def table(store,user):
    from crm_automation_home_data import counts,rows,PAGE_SIZE
    state=home_state()
    c,_=resolve(state,store,('counts',None),job(state,store,('counts',None),lambda:counts(store)),fields=('all_count','drafts','active','paused','archived'))
    with st.container(key='crm-home-list'):
        labels=dict(zip(TABS,('all_count','drafts','active','paused','archived')))
        tab=st.segmented_control('Automation status',TABS,default=TABS[0],format_func=lambda t:t+' '+str((c or {}).get(labels[t],'—')),key='crm-home-tabs') or TABS[0]
        st.html('<style>.st-key-crm-home-tabs button:nth-child('+str(TABS.index(tab)+1)+'){border-bottom:2px solid #c7a13f!important;color:#161616!important;font-weight:600}</style>')
        with st.container(key='crm-home-controls'):
            search,filter_col,sort=st.columns([3,1,1])
            query=search.text_input('Search automations',placeholder='Search automations...',label_visibility='collapsed',key='auto_search')
            trigger=filter_col.selectbox('Trigger',['All',*TRIGGERS],format_func=lambda t:'All triggers' if t=='All' else TRIGGERS[t][1],label_visibility='collapsed',key='auto_filter')
            order=sort.selectbox('Sort',['Newest first','Oldest first'],label_visibility='collapsed',key='auto_sort')
        criteria=(tab,query,trigger,order)
        if state.get('criteria')!=criteria:state['offset']=0;state['criteria']=criteria
        offset=state.get('offset',0);key=('table',criteria,offset)
        result,activity=resolve(state,store,key,job(state,store,key,lambda:rows(store,tab=tab,search=query,trigger=trigger,oldest=order=='Oldest first',offset=offset)))
        state.setdefault('activity',{})['table']=activity
        if activity=='ERROR':st.caption('List refresh failed. Previously verified rows are retained.')
        if result is None:st.caption('Loading automations…');return
        fields=('Automation','Trigger','Updated','Entered','Sent','Delivered','Opened','Clicked','Orders','Status')
        st.html('<div class="sc-auto-head">'+''.join('<div>'+f+'</div>' for f in fields)+'</div>')
        for row in result[:PAGE_SIZE]:
            with st.container(horizontal=True,key='auto-row-'+str(row['id'])):
                with st.container(width='stretch'):
                    updated=str(row['updated_at'])[:10]
                    values=(row['name'],TRIGGERS.get(row['trigger_type'],('', 'Legacy flow'))[1],updated,*[format(row[k],',') for k in ('entered','sent','delivered','opened','clicked','orders')],row['category'].rstrip('s').upper())
                    st.html('<div class="sc-auto-row">'+''.join('<div>'+escape(str(v))+'</div>' for v in values)+'</div>')
                with st.container(width=80,horizontal=True,gap='xxsmall',key='auto-actions-'+str(row['id'])):
                    with st.popover('Actions',key='auto_actions_'+str(row['id'])):
                        if st.button('Open',key='auto_open_'+str(row['id'])):open_flow(row['id'])
                        if row['format']=='automation_flow_v1' and st.button('Duplicate',key='auto_duplicate_'+str(row['id'])):
                            copy=store.duplicate(user,row['id']);changed();open_flow(copy['id'])
                        action={'Active':'pause','Paused':'resume'}.get(row['category']) if row['format']=='automation_flow_v1' else ('pause' if row['category']=='Active' else None)
                        if action and st.button(action.title(),key='auto_lifecycle_'+str(row['id'])):store.lifecycle(user,row['id'],action);changed();st.rerun(scope='fragment')
                        if row['category'] in ('Paused','Drafts') and st.button('Archive',key='auto_archive_'+str(row['id'])):store.lifecycle(user,row['id'],'archive');changed();st.rerun(scope='fragment')
                    if row['category'] in ('Drafts','Archived'):
                        with st.container(key='auto-trash-'+str(row['id'])):
                            if st.button('Delete automation',icon=':material/delete:',key='auto_delete_'+str(row['id']),help='Delete automation'):
                                delete_dialog(store,user,row)
        if not result:st.caption('No automations match this view.')
        previous,next_col=st.columns(2)
        if previous.button('Previous',disabled=offset==0,key='auto_previous'):state['offset']=max(0,offset-PAGE_SIZE);st.rerun(scope='fragment')
        if next_col.button('Next',disabled=len(result)<=PAGE_SIZE,key='auto_next'):state['offset']=offset+PAGE_SIZE;st.rerun(scope='fragment')


@st.fragment
def home(store,user):
    st.html(STYLE)
    st.html('''<style>.sc-auto-head,.sc-auto-row{display:grid;grid-template-columns:minmax(150px,2.5fr) minmax(90px,1.3fr) 76px repeat(6,minmax(32px,.55fr)) 65px;gap:8px;align-items:center;font-size:12px;min-width:0;padding:12px 0;border-bottom:1px solid #eee}.sc-auto-head{font-size:10px;color:#777}.sc-auto-row>div{min-width:0;overflow-wrap:anywhere}
    .sc-auto-head{margin-right:88px;position:relative}.sc-auto-head::after{content:"Actions";position:absolute;right:-88px;width:80px;text-align:center}
    [class*="st-key-auto-actions-"]{flex-wrap:nowrap!important}
    [class*="st-key-auto-actions-"]>[data-testid="stLayoutWrapper"]{width:36px!important;flex:0 0 36px!important}
    [class*="st-key-auto-row-"] [data-testid="stPopover"]{width:36px!important;flex:0 0 36px!important}
    [class*="st-key-auto-row-"] [data-testid="stPopover"] button{width:36px!important;padding:4px!important}
    [class*="st-key-auto-row-"] [data-testid="stPopover"] button p{font-size:0!important}
    [class*="st-key-auto-row-"] [data-testid="stPopover"] button p::after{content:"⋯";font-size:18px}
    [class*="st-key-auto-row-"] [data-testid="stPopover"] button svg{display:none}
    [class*="st-key-auto-row-"]{gap:8px!important}[class*="st-key-auto-row-"] button{min-height:36px}
    [class*="st-key-auto-trash-"] button{width:36px!important;height:36px!important;padding:5px!important}[class*="st-key-auto-trash-"] button p{font-size:0!important}
    .st-key-crm-campaign-home button[kind="primary"]{background:#c8a346!important;color:#141414!important;border-color:#c8a346!important}
    .st-key-crm-home-tabs button[aria-pressed="true"]{border-bottom:2px solid #c7a13f!important;color:#161616!important;font-weight:600}
    .sc-auto-row>div:last-child{display:inline-block;padding:4px 6px;background:#f4f2ed;border-radius:6px;font-size:11px;text-align:center}
    @media(max-width:1000px){.sc-auto-head>div:nth-child(3),.sc-auto-row>div:nth-child(3),.sc-auto-head>div:nth-child(7),.sc-auto-row>div:nth-child(7),.sc-auto-head>div:nth-child(9),.sc-auto-row>div:nth-child(9){display:none}.sc-auto-head,.sc-auto-row{grid-template-columns:minmax(120px,2fr) 85px repeat(4,minmax(32px,.6fr)) 60px}}
    @media(max-width:700px){.sc-auto-head,.sc-auto-row{grid-template-columns:minmax(0,1.8fr) 48px 26px 45px;font-size:11px;gap:5px}.sc-auto-head>div:nth-child(4),.sc-auto-row>div:nth-child(4),.sc-auto-head>div:nth-child(6),.sc-auto-row>div:nth-child(6),.sc-auto-head>div:nth-child(8),.sc-auto-row>div:nth-child(8){display:none}}
    </style>''')
    with st.container(key='crm-campaign-home'):
        title,create=st.columns([3,1],vertical_alignment='center')
        title.html('<h1>Automations</h1><p style="color:#73747c">Create and manage trigger-based email flows.</p>')
        if create.button('+ Create automation',type='primary',use_container_width=True):chooser(store,user)
        metrics(store);table(store,user)
        with st.container(key='crm-auto-home-poll'):
            st.button('Refresh automation data',key='crm-auto-home-poll-tick')
        st.html('<style>.st-key-crm-auto-home-poll{display:none}</style>')
    from crm_campaign_home import arm_home_poll
    pending=any(s in ('UNRESOLVED','LOADING','REFRESHING') for s in home_state().get('activity',{}).values())
    arm_home_poll(key='crm-auto-home-poll',seconds=.25 if pending else 20)


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
    editor['document']['copy_reviewed']=st.checkbox('This email copy is reviewed',value=editor['document']['copy_reviewed'],key=key+'reviewed')
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
    from crm_email_size_ui import size_meter
    user=actions.user;row=store.flow(identity);flow=row['config']['draft'];readonly=status(row)=='ARCHIVED'
    if st.button('← Automations',key='auto_back'):
        if flush_current():st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None);st.rerun()
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
    cfg=store.render_settings();composer_styles()
    st.html('''<style>
    .st-key-crm-automation-editor [data-testid="stVerticalBlock"]{gap:8px}
    .st-key-crm-automation-editor h3{margin:0;padding:0;font-size:20px}
    .st-key-crm-automation-editor .st-key-crm-composer-preview{padding:12px;gap:6px}
    .st-key-crm-automation-editor .st-key-crm-composer-preview iframe{height:clamp(340px,calc(100dvh - var(--sc-topbar-height,64px) - 250px),680px)!important}
    .st-key-crm-automation-editor button[kind="primary"]{background:#c8a346!important;border-color:#b99436!important;color:#141414!important}
    @media(max-width:760px){
    .st-key-crm-automation-editor .st-key-crm-composer-layout{flex-wrap:wrap!important}
    .st-key-crm-automation-editor .st-key-crm-composer-layout>div:has(>.st-key-crm-composer-controls){width:100%!important;flex-basis:100%!important}
    .st-key-crm-automation-editor .st-key-crm-composer-controls{width:100%!important;min-width:0!important;height:auto!important;max-height:none!important;overflow:visible!important}
    .st-key-crm-automation-editor .st-key-crm-composer-layout>div:has(>.st-key-crm-composer-preview){width:100%!important;flex-basis:100%!important;min-width:0!important}
    .st-key-crm-automation-editor .st-key-crm-composer-preview{width:100%!important;max-width:100%!important;box-sizing:border-box!important}
    }
    </style>''')
    key='auto_'+str(identity)+'_'+step['step_id']+'_'
    if readonly:
        from crm_html_workspace import composer_canvas
        with st.container(horizontal=True,gap='small'):
            with st.container(width=360):flow_email_control(flow,identity,selected)
            with st.container(width='stretch'):composer_canvas(editor['document'],cfg,key,store)
        return
    with st.container(horizontal=True,vertical_alignment='center'):
        with st.container(width='stretch'):size_meter(editor,key,cfg)
        if st.button('Save draft',key=key+'save'):
            if flush_current(force=True):changed();st.toast('Draft saved')
        from crm_abandoned_checkout_ui import live_control
        live_control(store,editor,key,cfg)
        test_control(store,user,editor,key,cfg=cfg)
        if st.button('Publish now',type='primary',key=key+'publish'):
            try:
                if not flush_current(force=True):return
                store.publish(user,identity,editor['version']);changed()
                st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None)
                st.session_state['automation_notice']='Automation published · listening for future events';st.rerun()
            except (ValueError,StoreUnavailable,PermissionError) as exc:st.error(safe_error(exc))
    composer_form(shop,store,actions,editor,key,cfg,None,True,mode='automation',settings_control=settings_control)
    st.session_state[key+'editor_emitted']=True
    if st.toggle('Show email step analytics',key='auto_step_stats'):
        from crm_automation_home_data import step_metrics
        names={s['step_id']:'Email '+str(i+1)+' · '+s['document']['content']['subject'] for i,s in enumerate(flow['emails'])}
        st.dataframe([{'Email':names.get(r['step_id'],'Previous version email'),**{k.title():v for k,v in r.items() if k!='step_id'}} for r in step_metrics(store,identity)],hide_index=True,use_container_width=True)


def workspace(shop,base,actions,navigate=lambda _:None):
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
        else:home(store,actions.user)
    except (StoreUnavailable,ValueError,PermissionError) as exc:st.warning(str(exc))
