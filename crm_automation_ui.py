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
    request_route(identity)
    st.rerun()


def request_route(identity):
    """Apply at the next workspace mount, before the bound widget renders."""
    st.session_state['_automation_navigation_target']=str(identity or '')
    st.session_state['_automation_navigation_email']=''


def request_email(identity):
    st.session_state['_automation_navigation_email']=str(identity or '')
    if identity:st.session_state['automation_step']=str(identity)


@st.dialog('Create automation',width='small')
def chooser(store,user):
    st.caption('Choose a trigger. Publishing listens for future events only.')
    st.caption('Win Back uses a scheduled customer inactivity scan. Identifiable abandoned-cart events are not available; checkout recovery uses verified Shopify checkouts.')
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
def home(store,user,shop=None,*,styles=True):
    from crm_automation_home import home as render_home
    render_home(shop,store,user,styles=styles)


def flow_email_control(flow,identity,selected):
    from crm_campaign_recovery import flush_current
    selection=st.selectbox('Flow email',list(range(len(flow['emails']))),index=next(i for i,s in enumerate(flow['emails']) if s['step_id']==selected),format_func=lambda i:'Email '+str(i+1)+' · '+(flow['emails'][i]['document']['content']['subject'] or 'Untitled')+' · '+str(flow['emails'][i]['delay_seconds']//60)+' min delay',key='auto_flow_step_'+str(identity)+'_'+str(len(flow['emails'])))
    if flow['emails'][selection]['step_id']!=selected:
        if not flush_current():return
        request_email(flow['emails'][selection]['step_id'])
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
        request_email(definition['emails'][index+1]['step_id']);st.session_state.pop('automation_editor',None);st.rerun()
    add,blank=st.columns(2)
    for column,label,duplicate in ((add,'+ Add email · duplicate previous',True),(blank,'+ Add email · start blank',False)):
        if column.button(label,key=key+str(duplicate)):
            if not flush_current(force=True):return
            current=store.flow(editor['id']);new=deepcopy(current['config']['draft'])
            new['emails'].append(email_step(new['emails'][-1]['document'] if duplicate else None,86400))
            saved=store.save_flow(user,editor['id'],editor['name'],new,current['config']['revision'])
            request_email(saved['config']['draft']['emails'][-1]['step_id'])
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
    from crm_automation_timing import delay_controls
    initial,unit=delay_controls(step['delay_seconds'])
    amount_slot,unit_slot=st.columns([2,1])
    with amount_slot:delay=st.number_input('Delay',min_value=0,max_value=525600,value=initial,step=1,key=key+'delay')
    with unit_slot:units=st.selectbox('Delay unit',['Minutes','Hours','Days'],index=['Minutes','Hours','Days'].index(unit),key=key+'delay_unit')
    st.caption('Flow status · '+status(row)+' · fresh consent and suppressions checked before every email')
    desired=deepcopy(flow);desired.update(trigger=kind,rules=rules,reentry_days=days)
    store.preview_trigger=kind
    next(s for s in desired['emails'] if s['step_id']==store.step_id)['delay_seconds']=step['delay_seconds'] if (delay,units)==(initial,unit) else int(delay)*{'Minutes':60,'Hours':3600,'Days':86400}[units]
    if desired!=flow:
        from crm_automation_definition import validate
        try:validate(desired)
        except ValueError as exc:st.caption(str(exc));return
        # Include current content in the same optimistic write.
        next(s for s in desired['emails'] if s['step_id']==store.step_id)['document']=deepcopy(editor['document'])
        updated=store.save_flow(user,row['id'],editor['name'],desired,editor['version'])
        editor['version']=updated['config']['revision']
    add_email_controls(store,user,editor,key)


def detail(shop,store,actions,identity,*,row=None):
    store.preview_shop=shop
    template_view=st.session_state.get('automation_template_view')
    if template_view:
        fn,args,kwargs=template_view
        fn(*args,**kwargs)
        return
    user=actions.user;row=store.flow(identity,row=row);flow=row['config']['draft'];readonly=status(row)=='ARCHIVED'
    if not st.session_state.get('automation_composing'):
        from crm_flow_page import flow_page
        flow_page(shop,store,user,row)
        return
    from crm_campaign_page import composer_form
    from crm_campaign_recovery import flush_current
    from crm_html_workspace import html_document,composer_styles
    selected=st.session_state.get('automation_step')
    if selected not in [s['step_id'] for s in flow['emails']]:selected=flow['emails'][0]['step_id']
    step=next(s for s in flow['emails'] if s['step_id']==selected)
    if store.step_id!=step['step_id']:store.step_id=step['step_id']
    editor=st.session_state.get('automation_editor')
    if editor and (str(editor['id'])!=str(identity) or st.session_state.get('automation_step')!=step['step_id']):
        if not flush_current():return
        editor=None;row=store.flow(identity);flow=row['config']['draft']
    if editor is None:
        from crm_email_editor_context import editable_document
        editor=store.draft(identity,row=row);editor['document']=editable_document(editor['document'])
        # Normalize the editable representation before taking its clean baseline.
        # Nothing is persisted until an operator actually edits it.
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
    from crm_automation_toolbar import toolbar
    toolbar(store,user,identity,editor=editor,key=key,cfg=cfg)
    if readonly:
        from crm_html_workspace import composer_canvas
        with st.container(horizontal=True,gap='small'):
            with st.container(width=360):flow_email_control(flow,identity,selected)
            with st.container(width='stretch'):composer_canvas(editor['document'],cfg,key,store)
        return
    # The toolbar just rendered this exact snapshot. Only a subsequent edit
    # needs its independent refresh; mounting the composer is not an edit.
    st.session_state['_automation_toolbar_value']=(editor['name'],editor.get('version'),False,st.session_state.get('campaign_save_status'))
    composer_form(shop,store,actions,editor,key,cfg,None,True,mode='automation',settings_control=settings_control)
    st.session_state[key+'editor_emitted']=True


@st.fragment
def workspace(shop,base,actions,navigate=lambda _:None):
    from crm_navigation import require
    # A fragment event still passes the active account/permission gate. The
    # shared OS session is authoritative when present; fixtures supply an actor.
    account=st.session_state.get('sports_cave_current_user') or actions.user
    if 'sports_cave_authenticated' in st.session_state and not st.session_state['sports_cave_authenticated']:
        raise PermissionError('Sign in before opening Automations.')
    require(account,'crm_automations_manage')
    if st.session_state.get('email_editor_mode')!='automation':
        st.session_state.pop('_automation_preview_open',None)
    st.session_state['email_editor_mode']='automation'
    store=AutomationStore(base.connect)
    if '_automation_route_restore' in st.session_state:
        restored=st.session_state.pop('_automation_route_restore')
        st.session_state['automation']=restored[0] or ''
        st.session_state['automation_email']=restored[1] or ''
        import json
        values=json.dumps({'automation':restored[0] or '', 'automation_email':restored[1] or ''}).replace('<',r'\u003c')
        # A failed save vetoes the client navigation. Restore its URL without
        # adding history or attempting another save; bound fields restore state.
        st.html('<script>(()=>{const target=new URL(location.href);for(const [key,value] of Object.entries('+values+')){if(value)target.searchParams.set(key,value);else target.searchParams.delete(key);}history.replaceState({},"",target);})();</script>',unsafe_allow_javascript=True)
        st.warning('Save failed. Your automation edits are retained; retry before leaving.')
    if '_automation_navigation_target' in st.session_state:
        st.session_state['automation']=st.session_state.pop('_automation_navigation_target')
    if '_automation_navigation_email' in st.session_state:
        st.session_state['automation_email']=st.session_state.pop('_automation_navigation_email')
    previous=st.session_state.get('_automation_route_observed')
    previous_email=st.session_state.get('_automation_email_observed')
    if '_automation_route_observed' not in st.session_state and not st.query_params.get('automation') and 'automation' not in st.session_state:
        # Retain the initial legacy in-session entry point. Thereafter the URL
        # is authoritative, including native Streamlit Back/Forward reruns.
        if st.session_state.get('automation_selected'):st.session_state['automation']=str(st.session_state['automation_selected'])
    # Streamlit's supported binding keeps its frontend query snapshot in sync
    # with native widget events, including the existing browser-history bridge.
    st.html('<style>.st-key-automation,.st-key-automation_email{display:none}</style>')
    identity=st.text_input('Automation route',key='automation',bind='query-params') or None
    email=st.text_input('Automation email route',key='automation_email',bind='query-params') or None
    from pathlib import Path
    st.html('<script>'+Path(__file__).with_name('components').joinpath('crm_sections','automation_navigation.js').read_text(encoding='utf8')+'</script>',unsafe_allow_javascript=True)
    if previous!=identity or previous_email!=email:
        from crm_campaign_recovery import flush_current
        if not flush_current(force=True):
            st.session_state['_automation_route_restore']=(previous,previous_email)
            st.rerun(scope='app')
        else:
            st.session_state['automation_composing']=bool(email)
            if email:st.session_state.update(automation_step=email,flow_return_step=email)
            st.session_state.pop('automation_template_view',None)
            if previous!=identity:st.session_state.pop('flow-operational-diagnostics',None)
            st.session_state.pop('automation_editor',None)
            st.session_state['_automation_route_observed']=identity
            st.session_state['_automation_email_observed']=email
    if identity:st.session_state['automation_selected']=str(identity)
    else:st.session_state.pop('automation_selected',None)
    from html import escape
    st.html('<span hidden data-automation-route="'+escape(str(identity or ''),quote=True)+'" data-automation-email="'+escape(str(email or ''),quote=True)+'"></span>')
    # Keep critical overview styles at a stable delta position while its old
    # subtree is removed. A route placeholder replaces that subtree before any
    # blocking editor read; it must never be reconciled with editor columns.
    from crm_automation_home import STYLE,STYLE_AUTO
    st.html(STYLE+STYLE_AUTO+'''<style>
    .sc-auto-editor-loading{min-height:38px;display:flex;align-items:center;color:#73747c;font-size:13px}
    </style>''')
    # Distinct delta slots matter: empty()+container() in one slot is coalesced
    # by Streamlit and retains the old block's children until script completion.
    # Clear the inactive slot without replacing it during the same run.
    overview_route=st.empty();flow_route=st.empty()
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
            overview_route.empty()
            with flow_route.container(key='automation-flow-route'):editor_dialog(shop,store,actions,identity)
        else:
            st.session_state.pop('_automation_preview_open',None)
            flow_route.empty()
            with overview_route.container(key='automation-overview-route'):home(store,actions.user,shop=shop,styles=False)
    except (StoreUnavailable,ValueError,PermissionError) as exc:st.warning(str(exc))


@st.fragment
def editor_dialog(shop,store,actions,identity):
    # Compatibility name: this is a normal route fragment, never a dialog.
    # One placeholder replaces Flow and the shared composer atomically.
    with st.container(key='crm-automation-editor'):
        content=st.empty()
        content.html('<div class="sc-auto-editor-loading" role="status">Opening automation…</div>')
        try:
            existing=current_display_row(store,st.session_state,str(uuid.UUID(str(identity))))
            with content.container():
                from crm_automation_definition import native
                if existing and not native(existing):
                    st.subheader(existing['name']);st.caption('Legacy '+existing['status'].lower()+' flow · runtime and audit history retained')
                    if st.button('← Automations',key='legacy_auto_back'):
                        request_route(None);st.rerun(scope='app')
                    if existing['status']=='DRAFT' and existing['trigger_type'] in TRIGGERS and st.button('Convert draft to shared editor'):
                        store.adopt(actions.user,identity);changed();st.rerun(scope='app')
                    if existing['status']=='ACTIVE' and st.button('Pause legacy flow'):
                        store.lifecycle(actions.user,identity,'pause');changed();st.rerun(scope='app')
                    # Legacy records keep their existing adoption restrictions,
                    # but their analytics must remain accessible at this route.
                    from crm_flow_page import summary,recent
                    from crm_checkout_analytics import PERIODS
                    period=st.selectbox('Date range',list(PERIODS),index=4,key='auto-analytics-period-'+str(identity))
                    summary(store,identity,period);recent(store,existing,actions.user,period)
                else:
                    with store.display_read_scope():
                        requested=st.session_state.get('_automation_email_observed')
                        if requested and requested not in [s['step_id'] for s in store.flow(identity,row=existing)['config']['draft']['emails']]:raise ValueError('Email step is unavailable. Return to Flow to choose an existing email.')
                        detail(shop,store,actions,identity,row=existing)
        except (StoreUnavailable,ValueError,PermissionError) as exc:
            with content.container():
                st.error(str(exc))
                if st.button('Retry opening editor'):st.rerun(scope='fragment')
                if st.button('← Automations',key='editor-error-back'):
                    request_route(None);st.rerun(scope='app')


def current_display_row(store,state,identity):
    """A fresh marker authorizes reuse of this session's full display row.

    Legacy, changed, deleted and uncached records still use the full read.
    This is never used for mutations or immutable published-source selection.
    """
    cached=state.get('_automation_toolbar_definition')
    from crm_automation_definition import native
    if cached and cached[0][0]==str(identity) and str(cached[1].get('id'))==str(identity) and native(cached[1]):
        marker=store.q('SELECT updated_at FROM crm_automations WHERE id=%s',(identity,),True)
        if marker and cached[0][1]==marker['updated_at']:return cached[1]
    return store.get('automations',identity)
