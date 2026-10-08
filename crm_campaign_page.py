"""Compact Campaigns V1 workspace. Explicit buttons are the only external-I/O triggers."""
from sports_categories import sport_category_options, normalize_sport_state
from copy import deepcopy
import json
import uuid
import streamlit as st
import streamlit.components.v1 as components
import os_accounts
from crm_campaign_content import (TYPES,MARKETS,OBJECTIVES,FIELDS,new_document,settings,
                                  preflight,render_campaign,prompt_for,parse_copy)
from crm_campaign_store import CampaignStore
from crm_campaign_library import COMPOSER_TARGET
from crm_audience import count_page
from crm_logic import rule
from crm_store import StoreUnavailable
from crm_email_blocks import PURPOSES, STARTERS, KINDS, block, starter, duplicate_block, legacy_blocks
from crm_campaign_content import html_budget
from crm_audience import selection_page
from crm_tracking import asset_url
from crm_resend_marketing import get_resend_marketing_config_status
from crm_logic import now
from crm_campaign_recovery import autosaving, flush_current, activate, restore


def open_editor(row):
    from crm_campaign_home_data import invalidate
    invalidate(st.session_state)
    st.session_state['campaign_view']='CAMPAIGN_EDITOR'
    st.session_state['campaign_show_drafts']=True
    st.session_state['campaign_list_generation']=st.session_state.get('campaign_list_generation',0)+1
    from crm_html_workspace import html_document
    st.session_state['campaign_editor']=deepcopy(row)
    st.session_state['campaign_editor']['document']=html_document(row['document'])
    editor=st.session_state['campaign_editor']
    from crm_campaign_markets import audience
    from crm_middle_sections import middle_sections,commit_middle
    editor['document']['market_audience']=True
    editor['document']['audience']=audience(editor['document']['market'])
    editor['document'].setdefault('send_timing',{'mode':'now'})
    commit_middle(editor['document'],middle_sections(editor['document']))
    editor['recovery_seed']=uuid.uuid4().hex
    st.session_state['campaign_saved']=deepcopy(editor)
    st.session_state.pop('campaign_save_error',None)
    st.session_state['campaign_save_status']='Saved' if row.get('id') else 'Ready · changes save automatically'
    context=st.session_state.get('campaign_recovery_context')
    if context:
        try:activate(*context,row.get('id'))
        except ValueError:
            editor['recovery_readonly']=True
            st.session_state.pop('campaign_recovery_context',None)
            st.session_state['campaign_save_status']='Read-only campaign'
    if row.get('id'):st.query_params['campaign']=str(row['id'])
    elif 'campaign' in st.query_params:del st.query_params['campaign']
    st.session_state['campaign_edit_key']=str(uuid.uuid4())


def dirty(editor):
    saved=st.session_state.get('campaign_saved',{})
    return editor.get('document')!=saved.get('document') or editor.get('name')!=saved.get('name')


def test_panel(store,user,editor,key,cfg,pending=None):
    """Collect intent only; dispatch happens after all editor widgets are read."""
    from hashlib import sha256
    doc=editor['document']
    digest=sha256(json.dumps({k:v for k,v in doc.items() if k!='copy_reviewed'},sort_keys=True).encode()).hexdigest()[:16]
    doc['copy_reviewed']=st.checkbox('Copy and subject reviewed',doc['copy_reviewed'],key=key+'review_'+digest)
    try:checks=preflight(doc,cfg=cfg)
    except ValueError as exc:
        st.caption(str(exc));return None
    with st.expander('Checks'):
        for label,ok in checks['test'].items():st.caption(('✓ ' if ok else '○ ')+label)
        st.caption('Live sending disabled. Production unsubscribe must be activated before any future live send.')
    if not os_accounts.can_access_page(user,'CRM Campaigns'):return None
    with st.form(key+'internal_test'):
        recipient=st.text_input('Test recipient',value='')
        confirmed=st.checkbox('One manually entered test recipient')
        send=st.form_submit_button('Send internal test',disabled=not editor.get('id') or not checks['test_ready'] or bool(editor.get('archived_at')))
    if dirty(editor) if pending is None else pending:st.caption('Save reviewed content before testing.')
    if st.button('New test attempt',key=key+'new_test'):st.session_state[key+'test_operation']=str(uuid.uuid4())
    if st.session_state.get(key+'receipt'):st.success(st.session_state[key+'receipt'])
    return {'recipient':recipient,'confirmed':confirmed} if send else None


def perform_test(store,user,editor,key,request):
    from crm_resend_marketing import DeliveryError
    if not editor.get('id'):st.warning('Save this draft before sending an internal test.');return
    saved=store.draft(editor['id'])
    if saved['document']!=editor['document'] or saved['version']!=editor['version']:st.warning('Save current content and review before sending a test.');return
    try:
        operation=st.session_state.setdefault(key+'test_operation',str(uuid.uuid4()))
        result=store.test_campaign(user,editor['id'],editor['version'],operation_id=operation,**request)
        st.session_state[key+'receipt']='Test accepted by Resend · '+result['message_id']+' · '+str(result['accepted_at'])
        editor['status']=store.draft(editor['id'])['status']
        if not result['audit_saved']:st.warning('Test accepted; receipt storage needs review. Do not resend.')
        else:st.success(st.session_state[key+'receipt'])
    except (ValueError,PermissionError,StoreUnavailable,DeliveryError) as exc:st.warning(str(exc))


def html_templates(store,user,editor,key):
    from crm_html_workspace import html_document
    doc=editor['document'];templates=store.templates()
    if templates:
        selected=st.selectbox('Saved templates',templates,format_func=lambda t:t['name'],key=key+'html_template')
        confirmed=st.checkbox('Replace current HTML and subject',key=key+'replace_html')
        if st.button('Load template',disabled=not confirmed):
            snapshot=html_document(store.template_document(selected))
            doc.pop('html_sections',None)
            if 'html_sections' in snapshot:doc['html_sections']=deepcopy(snapshot['html_sections'])
            doc.pop('middle_sections',None)
            if 'middle_sections' in snapshot:doc['middle_sections']=deepcopy(snapshot['middle_sections'])
            doc.update(custom_html=snapshot['custom_html'],content_mode='HTML',content=snapshot['content'],template_ref={'id':str(selected['id']),'name':selected['name'],'version':selected['version']})
            reset_widgets();st.rerun()
    if os_accounts.can_access_page(user,'crm_templates_manage'):
        name=st.text_input('Template name',key=key+'template_name')
        if st.button('Save as template',disabled=dirty(editor)):store.save_design(user,name,doc);st.success('Template saved')


def _close_delete_dialog():
    st.session_state.pop('campaign_delete_dialog_id',None)


@st.dialog('Delete draft',on_dismiss=_close_delete_dialog)
def delete_dialog(store,user,editor):
    st.write('Delete “'+editor['name']+'”?')
    st.warning('This removes the unsent draft from the active list. Its revisions and audit history are retained.')
    with st.container(horizontal=True):
        cancel=st.button('Cancel')
        confirm=st.button('Delete draft',type='primary',key='confirm_delete_'+str(editor['id']))
    if cancel:_close_delete_dialog();st.rerun()
    if confirm:
        try:
            result=store.delete_draft(user,editor['id'],editor['version'],confirmed=True,confirmed_name=editor['name'])
            if str(st.session_state.get('campaign_editor',{}).get('id'))==str(editor['id']):
                st.session_state.pop('campaign_editor',None);st.session_state.pop('campaign_saved',None)
            st.session_state['campaign_delete_notice']='Draft deleted.' if result['audit_saved'] else 'Draft deleted. Activity log could not be recorded.'
            from crm_campaign_home_data import invalidate
            invalidate(st.session_state)
            _close_delete_dialog()
            st.rerun()
        except (ValueError,StoreUnavailable) as exc:st.error(str(exc))


def new_compose(smart_hours=16,cfg=None,sections=None):
    """Empty composer; first meaningful edit creates a durable checkpoint."""
    from crm_campaign_sections import section_defaults
    doc=new_document();doc.update(content_mode='HTML',custom_html='',smart_hours=smart_hours,html_sections=deepcopy(sections) if sections is not None else section_defaults(cfg or settings()))
    if cfg and 'email_defaults' in cfg:doc['html_sections']=deepcopy(cfg['email_defaults'])
    open_editor({'id':None,'version':None,'name':'Untitled campaign','status':'DRAFT',
                 'archived_at':None,'last_tested_at':None,'document':doc})


def recent_campaigns(drafts,key,user):
    """Compatibility entry point; the only campaign list is now Home."""
    from crm_campaign_home import home
    home(drafts,user)


@st.fragment(**({'key':COMPOSER_TARGET} if COMPOSER_TARGET else {}))
@autosaving
def composer_form(shop,drafts,actions,editor,key,cfg,choices,available,*,mode='campaign',settings_control=None):
    """Content interactions repaint only composer/preview; no workspace DB reads."""
    closing=st.session_state.pop('campaign_template_close_dialog',None)
    if closing is not None:closing.close()
    from crm_html_workspace import section_editor,composer_canvas
    from crm_recovery_ui import recovery_bridge
    if available and mode=='campaign':recovery_bridge(drafts,actions.user,editor,key)
    doc=editor['document'];c=doc['content']
    if 'email_defaults' in cfg:doc.setdefault('html_sections',deepcopy(cfg['email_defaults']))
    before=json.dumps({k:v for k,v in doc.items() if k!='copy_reviewed'},sort_keys=True)
    with st.container(horizontal=True,gap='small',key='crm-composer-layout'):
        with st.container(width=360,height=680,border=False,key='crm-composer-controls'):
            details,html_tab,templates_tab=st.tabs(['Settings','Editor','Templates'],key=key+'panel',on_change='rerun')
            with details:
                if details.open:
                    from crm_prompt_ui import prompt_control,field_feedback
                    if mode!='automation':prompt_control(shop,editor,key)
                    editor['name']=st.text_input('Automation name' if mode=='automation' else 'Campaign name',editor['name'],max_chars=150,key=key+'name')
                    c['subject']=st.text_input('Subject',c['subject'],max_chars=250,key=key+'subject')
                    c['preheader']=st.text_input('Preview text',c['preheader'],max_chars=250,key=key+'preheader')
                    if mode!='automation':field_feedback()
                    from crm_campaign_controls import market_control,timing_control
                    if mode=='automation':
                        if settings_control:settings_control(editor,key)
                    else:
                        market_control(shop,drafts,doc,key)
                        timing_control(doc,key)
            with html_tab:
                if html_tab.open:
                    from crm_email_prompt_ui import email_prompt_control
                    if mode!='automation':email_prompt_control(shop,editor,key)
                    section_editor(doc,cfg,key,drafts if available else None,actions.user,choices if available else None,shop)
            with templates_tab:
                if templates_tab.open and available:
                    from crm_brand_template_ui import brand_templates_settings
                    brand_templates_settings(drafts,actions.user,cfg,target=COMPOSER_TARGET)
                    st.divider()
                    from crm_campaign_library import library
                    library(drafts,actions.user,doc,target=COMPOSER_TARGET)
        with st.container(width='stretch'):composer_canvas(doc,cfg,key,drafts if available else None)
    if before!=json.dumps({k:v for k,v in doc.items() if k!='copy_reviewed'},sort_keys=True):doc['copy_reviewed']=False
    flush_current()
    from html import escape
    st.html('<p id="sc-campaign-save-status" role="status" style="font-size:13px;color:#777">'+escape(st.session_state.get('campaign_save_status','Saved'))+'</p>')
    if st.session_state.get('campaign_save_error'):
        st.warning(st.session_state['campaign_save_error'])
        if st.button('Retry save',key=key+'retry_save'):
            if mode=='automation':flush_current(force=True);return
            from crm_recovery_ui import retry_browser
            if not retry_browser(drafts,actions.user,editor,key):flush_current(force=True)
        if mode=='campaign' and st.button('Save separate recovery copy',key=key+'recovery_copy'):
            pending=st.session_state.pop('campaign_browser_recovery',None)
            if pending:editor.update(pending['editor'])
            editor['id']=None;editor['version']=None;editor['recovery_seed']=uuid.uuid4().hex
            if flush_current(force=True):open_editor(editor);st.rerun()



def continue_campaign_leave(drafts,navigate):
    target=st.session_state.pop('crm_requested_route',None)
    pending=st.session_state.pop('campaign_pending_open',None)
    if target:navigate(target)
    elif pending=='home':
        from crm_campaign_home import return_home
        return_home()
    elif pending=='new':
        cfg=drafts.render_settings()
        new_compose(drafts.setting('sending')['value']['smart_hours'],cfg,drafts.default_sections(cfg))
        if st.session_state.pop('campaign_open_templates',False):
            st.session_state[st.session_state['campaign_edit_key']+'panel']='Templates'
    elif pending:open_editor(drafts.draft(pending))
    st.rerun()


@st.fragment
def campaign_workspace(shop,store,actions,navigate=lambda _:None):
    st.session_state['email_editor_mode']='campaign'
    from email_loading import stage
    from crm_html_workspace import composer_styles
    composer_styles()
    drafts=CampaignStore(store.connect)
    editor=st.session_state.get('campaign_editor')
    explicit=st.query_params.get('campaign')
    if editor and explicit and str(editor.get('id') or '')!=explicit:
        try:identity=str(uuid.UUID(explicit))
        except ValueError:
            st.warning('Invalid campaign identity.');return
        st.session_state['campaign_pending_open']=identity
        # Keep the current route while the existing leave dialog protects edits.
        # Opening the target sets its URL; cancelling leaves the current URL.
        if editor.get('id'):st.query_params['campaign']=str(editor['id'])
        else:del st.query_params['campaign']
    if editor and dirty(editor) and (st.session_state.get('crm_requested_route') or st.session_state.get('campaign_pending_open')):
        from crm_campaign_leave_ui import leave_dialog
        leave_dialog(actions.user,lambda:continue_campaign_leave(drafts,navigate))
        return
    if st.session_state.get('crm_requested_route') or st.session_state.get('campaign_pending_open'):
        continue_campaign_leave(drafts,navigate)
        return
    view=st.session_state.setdefault('campaign_view','CAMPAIGNS_HOME')
    if explicit:
        view='CAMPAIGN_EDITOR'
        st.session_state['campaign_view']=view
    if view=='CAMPAIGNS_HOME':
        from crm_campaign_home import home
        home(drafts,actions.user)
        return
    st.html('''<style>
      [data-testid="stMainBlockContainer"]:has(.st-key-crm-selected-campaign){max-width:none;padding:calc(var(--sc-topbar-height,64px) + 8px) 18px 10px !important}
    </style>''')
    def back():st.session_state['campaign_pending_open']='home'
    st.button('← Campaigns',key='campaign_back_home',type='tertiary',on_click=back)
    with st.container(key='crm-selected-campaign'):
        with stage('Campaigns','editor_render'):
            _selected_campaign(shop,store,actions,navigate,drafts)


def _selected_campaign(shop,store,actions,navigate,drafts):
    from crm_html_workspace import composer_styles
    from email_loading import stage
    available=True
    try:
        with stage('Campaigns','selected_config'):
            cfg=drafts.render_settings()
            choices=None
    except StoreUnavailable as exc:
        available=False;cfg=settings()
        st.error(str(exc));st.caption('Persistence unavailable. Your compose state stays in this session; saves and tests are disabled.')
    st.session_state['campaign_persistence_unavailable']=not available
    if available:st.session_state['campaign_recovery_context']=(drafts,actions.user)
    else:st.session_state.pop('campaign_recovery_context',None)
    if not st.session_state.get('campaign_editor'):
        if not available:return  # Never replace an unavailable saved draft with defaults.
        try:
            explicit=st.query_params.get('campaign')
            with stage('Campaigns','selected_restore'):
                recovered=restore(drafts,actions.user,explicit)
            if not recovered and explicit:
                try:identity=str(uuid.UUID(str(explicit)))
                except ValueError:identity=None
                if identity and drafts.q('SELECT 1 FROM crm_campaigns WHERE id=%s',(identity,),True):
                    recovered=drafts.draft(identity)
            if recovered:open_editor(recovered)
            else:
                defaults=drafts.setting('sending')['value']
                new_compose(defaults['smart_hours'],cfg,cfg.get('email_defaults'))
        except StoreUnavailable as exc:
            st.error(str(exc));return

    editor=st.session_state['campaign_editor'];doc=editor['document'];c=doc['content']
    with stage('Campaigns','selected_delivery'):
        delivery=drafts.q('SELECT * FROM crm_campaigns WHERE id=%s',(editor['id'],),True) if available and editor.get('id') else None
    if delivery:
        # Frozen preview bypasses all authoring/autosave widgets and recovery writes.
        from crm_campaign_progress_ui import operational_view
        composer_styles()
        editor['recovery_readonly']=True
        st.session_state['campaign_saved']=deepcopy(editor)
        operational_view(drafts,actions.user,delivery)
        if st.session_state.get('crm_requested_route') or st.session_state.get('campaign_pending_open'):
            continue_campaign_leave(drafts,navigate)
        return
    from crm_campaign_markets import audience
    doc['market_audience']=True
    selected_audience=audience(doc['market'])
    if doc['audience']!=selected_audience:doc['audience']=selected_audience;doc['counts']={}
    key=st.session_state.setdefault('campaign_edit_key',str(uuid.uuid4()))
    composer_styles()
    if st.session_state.get('campaign_delete_notice'):st.info(st.session_state.pop('campaign_delete_notice'))
    title,buttons=st.columns([4,5],vertical_alignment='center')
    title.markdown('### '+('New Campaign' if not editor.get('id') else html_escape_name(editor['name']))+' · '+editor['status'])
    if not get_resend_marketing_config_status()['marketing_enabled']:
        title.caption('● Marketing delivery OFF · Tests only')
    with buttons.container(horizontal=True,horizontal_alignment='right',gap='small',key='crm-campaign-actions'):
        from crm_email_size_ui import size_meter
        st.session_state[key+'review_preview_settings']=cfg
        st.session_state[key+'editor_emitted']=False
        size_meter(editor,key,cfg)
        save=st.button('Save draft',type='secondary',disabled=not available or bool(editor['archived_at']) or bool(editor.get('recovery_readonly')))
        from crm_campaign_send_ui import test_control
        test_control(drafts,actions.user,editor,key,available,cfg=cfg)
        from crm_campaign_send_ui import send_control
        send_control(shop,drafts,actions.user,editor,key,cfg,available)
    new_requested=False
    composer_form(shop,drafts,actions,editor,key,cfg,choices if available else None,available)
    st.session_state[key+'editor_emitted']=True
    if available and not editor.get('archived_at') and not editor.get('recovery_readonly'):
        from crm_campaign_audience_prepare import prepare_session
        prepare_session(st.session_state,shop,drafts,editor,key,cfg)
    if save and flush_current(force=True):
        st.toast('Draft saved');st.rerun()
    if new_requested:st.session_state['campaign_pending_open']='new'
    target=st.session_state.get('crm_requested_route');pending=st.session_state.get('campaign_pending_open')
    if target or pending:
        if dirty(editor):
            from crm_campaign_leave_ui import leave_dialog
            leave_dialog(actions.user,lambda:continue_campaign_leave(drafts,navigate))
        else:continue_campaign_leave(drafts,navigate)



def html_escape_name(name):
    # Markdown title must not interpret campaign names as formatting or links.
    import re
    return re.sub(r'([\\`*_{}\[\]()#+.!|<>-])',lambda m:chr(92)+m.group(0),name)


def audience_editor(shop,store,doc,key,compact=False):
    if not compact:st.caption('RECIPIENTS · Existing Shopify customers and consent. No recipient list is stored with a draft.')
    a,b=(st.container(),st.container()) if compact else st.columns([3,1])
    if not compact:a.write('Include segments as a union. Exclusions always win.')
    old_hours=doc.get('smart_hours',16)
    doc['smart_hours']=int(b.number_input('Smart Sending · hours',1,168,int(old_hours),key=key+'frequency'))
    if old_hours!=doc['smart_hours']:doc['counts']={};st.session_state.pop(key+'count',None)
    if not compact:st.caption('Default 16 hours · based only on actual Sports Cave OS marketing sends, including future campaigns and flows. Excludes internal tests, support and transactional emails. External Klaviyo / Shopify Email history is not included.')
    mode=st.radio('Audience source',('All subscribed / filters','Saved segments'),horizontal=True,key=key+'source')
    current=json.dumps(doc['audience'],sort_keys=True)
    if mode.startswith('All'):
        cols=[st.container() for _ in range(4)] if compact else st.columns(4)
        country=cols[0].selectbox('Country',('Any','AU','US','GB'),key=key+'country')
        normalize_sport_state(st.session_state, key+'sport', 'Any')
        sport=cols[1].selectbox('Interest / sport',sport_category_options(controls=('Any',)),key=key+'sport')
        orders=cols[2].number_input('Minimum orders',0,10000,key=key+'orders')
        days=cols[3].selectbox('Last purchase',('Any','Last 30 days','Last 180 days','Over 180 days'),key=key+'days')
        if st.button('Use these filters'):
            rules=[rule('consent','SUBSCRIBED')]
            if country!='Any':rules.append(rule('country',country))
            if sport!='Any':rules.append(rule('interest',sport,'contains'))
            if orders:rules.append(rule('orders',orders,'gte'))
            if days!='Any':rules.append(rule('last_order_days',30 if days=='Last 30 days' else 180,'gte' if days.startswith('Over') else 'lte'))
            doc['audience']={'kind':'Selection','name':'Subscribed · '+country+' · '+sport,'include':[{'kind':'Rules','name':'Selected filters','rules':{'all':rules}}],'exclude':[]}
    if st.button('Load saved segments'):
        page=shop.segments();st.session_state[key+'segments']=[{'kind':'Shopify','name':s['name'],'id':s['id']} for s in page['nodes']]+[{'kind':'Rules','name':s['name'],'rules':s['rules']} for s in store.list('segments')]
        st.session_state[key+'segment_cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    if st.session_state.get(key+'segment_cursor') and st.button('Load more segments'):
        page=shop.segments(st.session_state[key+'segment_cursor']);st.session_state[key+'segments'] += [{'kind':'Shopify','name':s['name'],'id':s['id']} for s in page['nodes']]
        st.session_state[key+'segment_cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    options=st.session_state.get(key+'segments',[])
    if options:
        cols=[st.container(),st.container()] if compact else st.columns(2)
        included=cols[0].multiselect('Include segments',range(len(options)),format_func=lambda i:options[i]['name'],key=key+'include')
        excluded=cols[1].multiselect('Exclude segments',range(len(options)),format_func=lambda i:options[i]['name'],key=key+'exclude')
        if st.button('Apply segment selection'):
            if not included:st.warning('Choose at least one included segment.')
            else:doc['audience']={'kind':'Selection','name':' + '.join(options[i]['name'] for i in included)[:300],'include':[options[i] for i in included],'exclude':[options[i] for i in excluded]}
    if current!=json.dumps(doc['audience'],sort_keys=True):doc['counts']={};st.session_state.pop(key+'count',None)
    selection=doc['audience'] if doc['audience']['kind']=='Selection' else {'kind':'Selection','name':doc['audience']['name'],'include':[doc['audience']],'exclude':[]}
    st.caption('Selected: '+selection['name']+' · Only explicit SUBSCRIBED profiles are eligible. Purchase is not consent.')
    a,b=(st.container(),st.container()) if compact else st.columns(2);restart=a.button('Recalculate eligibility');previous=st.session_state.get(key+'count')
    more=b.button('Continue calculation',disabled=not previous or previous.get('complete',False))
    if restart or more:
        doc['counts']={}
        st.session_state.pop(key+'count',None)
        state=selection_page(shop,store,selection,previous if more else None,smart_hours=doc.get('smart_hours',16));st.session_state[key+'count']=state
        if state['complete']:doc['counts']={k:state[k] for k in ('members','eligible','excluded','complete','checked_at')}
        st.rerun()
    state=st.session_state.get(key+'count',doc['counts']);complete=state.get('complete',False)
    cols=[st.container() for _ in range(3)] if compact else st.columns(3)
    for col,label,value in zip(cols,('Matched profiles','Eligible estimate','Excluded'),(state.get('members','—'),state.get('eligible','—') if complete else 'Unavailable',sum(state.get('excluded',{}).values()) if complete else 'Unavailable')):
        if compact:col.caption(label+': '+str(value))
        else:col.metric(label,value)
    st.caption(('Complete' if complete else 'Not calculated / partial — continue all pages, including consent verification')+' · '+state.get('checked_at','')+' · Always recheck consent, suppression and frequency before future dispatch.')
    with st.expander('Exclusion reasons + calculation detail'):
        st.json({'primary_reasons':state.get('excluded',{}),'diagnostics':state.get('diagnostics',{}),'pages_scanned':state.get('pages',0)})


def layout_preview(doc,cfg,key):
    controls=st.columns([2,2])
    width=controls[0].selectbox('Layout width',(600,430,390,375,320),format_func=lambda w:'Desktop' if w==600 else str(w),key=key+'previewwidth')
    mode=controls[1].selectbox('Preview mode',('Images on','Images off','Plain text'),key=key+'previewmode')
    rendered=render_campaign(doc,cfg,images_off=mode=='Images off')
    st.caption('Layout preview · not a Gmail / Outlook certification')
    if mode=='Plain text':st.text_area('Plain-text alternative',rendered['text'],height=330,disabled=True,key=key+'plain')
    else:components.html(rendered['html'],width=width,height=330,scrolling=True)
    budget=html_budget(rendered['html']);st.caption(budget['label'])
    if budget['warning']:st.warning('HTML size needs review before testing.')


def message_editor(shop,store,user,editor,key,cfg):
    doc=editor['document'];c=doc['content'];before=json.dumps(doc,sort_keys=True)
    left=st.container()
    with left:
        delivery=get_resend_marketing_config_status()
        with st.expander('Sender + campaign details'):
            import os
            st.text_input('Sender name',os.getenv('RESEND_FROM_NAME',''),disabled=True)
            st.text_input('Sender address',delivery['sender'],disabled=True)
            st.text_input('Reply-To',delivery['reply_to'],disabled=True)
            st.caption('Approved sender configuration only. Change verified identity through the reviewed deployment configuration.')
            st.caption('Purpose: '+doc['type']+' · Segment: '+__import__('crm_campaign_markets').MARKET_LABELS[doc['market']])
            doc['notes']=st.text_area('Notes for prompt',doc['notes'],height=90,key=key+'notes')
            doc['offer']=st.text_input('Reviewed offer or None',doc['offer'],key=key+'offer')
            doc['offer_reviewed']=st.checkbox('I verified this offer',doc['offer_reviewed'],key=key+'offer_reviewed')
        with st.expander('Choose template / starter'):
            selected=st.selectbox('Starter layout',STARTERS,key=key+'starter')
            replace=st.checkbox('Replace the current design with the selected snapshot',key=key+'replace')
            if st.button('Use starter',disabled=bool(doc.get('blocks') or doc.get('custom_html')) and not replace):
                doc['content_mode']='Blocks';doc['blocks']=starter(selected);doc['template_ref']={'name':selected,'version':1};reset_widgets();st.rerun()
            templates=store.templates()
            if templates:
                t=st.selectbox('Saved template',templates,format_func=lambda t:t['name']+' · v'+str(t['version']),key=key+'template')
                if st.button('Use saved template',disabled=bool(doc.get('blocks') or doc.get('custom_html')) and not replace):
                    snapshot=store.template_document(t);doc['content_mode']=snapshot.get('content_mode','Blocks');doc['custom_html']=snapshot.get('custom_html',doc.get('custom_html',''));doc['blocks']=snapshot['blocks'];doc['content']=snapshot['content'];doc['template_ref']={'id':str(t['id']),'version':t['version'],'name':t['name']};reset_widgets();st.rerun()
            if os_accounts.can_access_page(user,'crm_templates_manage'):
                name=st.text_input('Save design as template',key=key+'designname')
                if st.button('Save as template'):store.save_design(user,name,doc);st.success('Versioned template saved. This campaign keeps its own snapshot.')
        if not doc.get('blocks'):
            if any(c.values()):
                if st.button('Edit existing content as blocks'):doc['content_mode']='Blocks';doc['blocks']=legacy_blocks(c);reset_widgets();st.rerun()
            else:st.info('Choose a starter or add a block. Brand header and compliance footer are locked.')
        with st.expander('Prompt factory'):
            from crm_prompt_factory import generate,parse,proposals,apply
            if st.button('Generate Sports Cave Prompt'):st.session_state[key+'prompt']=generate(doc,store.setting('prompts')['value'])
            if st.session_state.get(key+'prompt'):
                copy_prompt(st.session_state[key+'prompt']);st.code(st.session_state[key+'prompt'],language=None)
            pasted=st.text_area('Paste generated JSON',height=120,key=key+'paste')
            if st.button('Validate proposed copy'):st.session_state[key+'proposal']=parse(pasted,doc)
            proposal=st.session_state.get(key+'proposal')
            if proposal:
                with st.expander('Generated copy brief + options'):
                    st.json({k:proposal[k] for k in ('subject_options','preheader_options','copy')})
                changes=proposals(proposal,doc);st.dataframe([{'Field':k,**v} for k,v in changes.items()],hide_index=True)
                selected_fields=st.multiselect('Apply selected fields',list(changes),key=key+'copyselection')
                if st.button('Apply selected copy',disabled=not selected_fields):editor['document']=apply(doc,proposal,selected_fields);reset_widgets();st.rerun()


def reset_widgets():
    st.session_state['campaign_edit_key']=str(uuid.uuid4())
    if st.session_state.get('campaign_editor'):st.session_state['campaign_editor']['document']['copy_reviewed']=False


def block_editor(shop,doc,key):
    blocks=doc.setdefault('blocks',[])
    st.caption('DESIGN · Locked brand header above; locked compliance footer below.')
    from crm_block_editor import sortable
    index=sortable(doc,key)
    if blocks:
        b=blocks[index];bk=key+b['id'];kind=b['type']
        if kind in ('heading','text'):b['text']=st.text_area('Block copy',b['text'],height=110,key=bk+'text')
        elif kind=='image':
            b['url']=st.text_input('Image URL (public JPEG/PNG)',b['url'],key=bk+'url')
            b['alt']=st.text_input('Image alt text',b['alt'],key=bk+'alt');b['decorative']=st.checkbox('Decorative image',b['decorative'],key=bk+'decorative')
            image_picker(shop,b,bk)
        elif kind=='button':
            b['label']=st.text_input('Button label',b['label'],key=bk+'label');b['url']=st.text_input('Button HTTPS URL',b['url'],key=bk+'url')
        elif kind=='spacer':b['height']=int(st.number_input('Spacer height',8,64,b['height'],key=bk+'height'))
        elif 'products' in b:product_picker(shop,b,doc['market'],bk)
    st.caption('Images: public JPEG/PNG, 600–1000px wide; aim ≤1 MB. Shopify supplies a proportional JPEG derivative up to 1000px, without cropping. Other unsupported sources require conversion in the existing asset workflow. Asset byte size is not fetched automatically.')


def image_picker(shop,b,key):
    query=st.text_input('Find product images',key=key+'imagequery')
    if st.button('Search images',key=key+'imagesearch'):st.session_state[key+'imageproducts']=shop.campaign_products(query)['nodes']
    products=st.session_state.get(key+'imageproducts',[])
    images=[(p,i) for p in products for i in p.get('images',{}).get('nodes',[]) if asset_url(i.get('url',''))]
    if images:
        selected=st.selectbox('Existing Shopify image',images,format_func=lambda x:x[0]['title']+' · '+str(x[1].get('altText') or x[1].get('id')),key=key+'img')
        product=selected[0];page=product.get('images',{})
        if page.get('pageInfo',{}).get('hasNextPage') and st.button('More images for this product',key=key+'moreimg'):
            following=shop.campaign_images(product['id'],page['pageInfo']['endCursor'])
            product['images']={'nodes':page.get('nodes',[])+following['nodes'],'pageInfo':following['pageInfo']};st.rerun()
        if st.button('Use image',key=key+'useimg'):b['url']=selected[1]['url'];b['alt']=selected[1].get('altText') or selected[0]['title'];reset_widgets();st.rerun()


def product_picker(shop,b,market,key):
    query=st.text_input('Search Shopify products',key=key+'query')
    if st.button('Search products',key=key+'search'):
        page=shop.campaign_products(query);st.session_state[key+'products']=page['nodes'];st.session_state[key+'cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    if st.session_state.get(key+'cursor') and st.button('More products',key=key+'more'):
        page=shop.campaign_products(query,st.session_state[key+'cursor']);st.session_state[key+'products']+=page['nodes'];st.session_state[key+'cursor']=page['pageInfo'].get('endCursor') if page['pageInfo'].get('hasNextPage') else None
    products=st.session_state.get(key+'products',[])
    if products:
        p=st.selectbox('Shopify product',products,format_func=lambda p:p['title'],key=key+'product')
        image_page=p.get('images',{})
        if image_page.get('pageInfo',{}).get('hasNextPage') and st.button('More product images',key=key+'moreimages'):
            page=shop.campaign_images(p['id'],image_page['pageInfo']['endCursor'])
            p['images']={'nodes':image_page.get('nodes',[])+page['nodes'],'pageInfo':page['pageInfo']};st.rerun()
        images=[i for i in p.get('images',{}).get('nodes',[]) if asset_url(i.get('url',''))]
        img=st.selectbox('Product image',images,format_func=lambda i:i.get('altText') or i['id'],key=key+p['id']+'image') if images else {}
        if img:st.image(img['url'],width=120)
        if st.button('Select product',key=key+'select',disabled=len(b['products'])>=(4 if b['type']=='product_grid' else 1)):
            b['products'].append({'id':p['id'],'title':p['title'],'url':p.get('onlineStoreUrl') or '', 'image':img.get('url',''),'alt':img.get('altText') or p['title'],'market':market,'facts_checked_at':now().isoformat()});reset_widgets();st.rerun()
    if b['products']:
        index=st.selectbox('Selected artwork',range(len(b['products'])),format_func=lambda i:b['products'][i]['title'],key=key+'selected')
        p=b['products'][index];p['alt']=st.text_input('Artwork alt text',p.get('alt',''),key=key+str(index)+'alt')
        variant_key=key+p['id']+'variants_data'
        st.caption(p['title']+' · '+(p.get('currency','')+' '+p.get('price','') if p.get('price') else 'Price omitted')+' · Edition availability omitted until verified by an approved source.')
        if st.button('Load variants / segment price',key=key+'variants'):
            st.session_state[variant_key]=shop.campaign_variants(p['id'])
        variant_page=st.session_state.get(variant_key,{})
        variants=variant_page.get('nodes',[])
        if variant_page.get('pageInfo',{}).get('hasNextPage') and st.button('More variants',key=key+'morevariants'):
            page=shop.campaign_variants(p['id'],variant_page['pageInfo']['endCursor']);page['nodes']=variants+page['nodes'];st.session_state[variant_key]=page;st.rerun()
        if variants:
            v=st.selectbox('Variant for displayed price',variants,format_func=lambda v:v['title'],key=key+p['id']+'variant')
            if st.button('Use verified segment price',key=key+'price'):
                money=shop.campaign_price(v['id'],market)
                if money:p.update(variant_id=v['id'],variant_title=v['title'],market=market,price=money['amount'],currency=money['currencyCode'],facts_checked_at=now().isoformat());st.rerun()
                else:st.warning('Segment price unavailable. No price was added.')
        if st.button('Refresh canonical facts for comparison',key=key+'refreshproduct'):
            current=shop.products([p['id']],fresh=True)
            if current:
                diff={k:{'saved':p.get(k),'current':current[0].get(remote)} for k,remote in (('title','title'),('url','onlineStoreUrl')) if p.get(k)!=current[0].get(remote)}
                st.session_state[key+'factdiff']=diff
        if key+'factdiff' in st.session_state:st.json(st.session_state[key+'factdiff']);st.caption('Changed facts flagged; saved edits were not overwritten. Re-select the product to use current facts.')
        if st.button('Remove artwork',key=key+'removeproduct'):b['products'].pop(index);reset_widgets();st.rerun()


def review_editor(store,user,editor,key,cfg):
    doc=editor['document'];checks=preflight(doc,cfg=cfg)
    left,right=st.columns([4,7],gap='medium')
    with left:
        st.caption('REVIEW · '+checks['policy'])
        st.caption('Internal test checks: '+str(sum(checks['test'].values()))+' / '+str(len(checks['test']))+' passed')
        with st.expander('Internal test preflight',expanded=not checks['test_ready']):
            for label,ok in checks['test'].items():st.caption(('✓ ' if ok else '○ ')+label)
        with st.expander('Production readiness — blocked'):
            for label,ok in checks['live'].items():st.caption(('✓ ' if ok else '○ ')+label)
            st.caption('One-click unsubscribe production path not activated. Missing legal identity is shown as a test-only warning; no segment is automatically legally cleared.')
        a,b=st.columns(2)
        needs=a.button('Needs review',disabled=dirty(editor))
        ready=b.button('Mark test ready',disabled=dirty(editor) or not checks['test_ready'])
        if needs or ready:
            updated=store.save(user,editor['name'],doc,editor['id'],editor['version'],requested_status='NEEDS_REVIEW' if needs else 'TEST_READY')
            st.session_state['campaign_editor']=deepcopy(updated);st.session_state['campaign_saved']=deepcopy(updated);st.rerun()
        if os_accounts.can_access_page(user,'CRM Campaigns'):
            with st.form(key+'test',clear_on_submit=False):
                recipient=st.text_input('Manual internal test recipient',value='')
                confirmed=st.checkbox('I confirm one internal mailbox and the TEST ONLY footer / inactive unsubscribe warnings.')
                clicked=st.form_submit_button('Send internal test',disabled=not checks['test_ready'] or dirty(editor))
            if dirty(editor):st.caption('Save current changes before sending a test.')
            if clicked:
                saved=store.draft(editor['id'])
                if saved['document']!=doc:st.warning('Save the current revision before testing.')
                else:
                    operation=st.session_state.setdefault(key+'test_operation',str(uuid.uuid4()))
                    result=store.test_campaign(user,editor['id'],editor['version'],recipient=recipient,confirmed=confirmed,operation_id=operation)
                    editor['status']=store.draft(editor['id'])['status']
                    st.success('Test accepted by Resend');st.text(result['message_id']+'\n'+str(result['accepted_at']))
                    if not result['audit_saved']:st.warning('Receipt persistence needs review. Do not resend.')
            if st.button('Start a separate test attempt'):
                st.session_state[key+'test_operation']=str(uuid.uuid4());st.caption('New explicit test attempt prepared. Type and confirm the recipient before sending.')
        else:st.caption('Only an administrator can send a single-recipient test.')
        with st.expander('Test history'):
            st.dataframe([{k:r[k] for k in ('campaign_version','status','provider_id','created_at','delivered')} for r in store.test_history(editor['id'])],hide_index=True)
        with st.expander('Revision history'):st.dataframe(store.history(editor['id']),hide_index=True)
    with right:layout_preview(doc,cfg,key)


def copy_prompt(value):
    payload=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e')
    components.html('''<button id="copy" style="background:#d6a548;border:0;border-radius:8px;padding:12px 20px;cursor:pointer">Copy Prompt</button>
<script>document.getElementById('copy').onclick=async function(){const s='''+payload+''';
try { await navigator.clipboard.writeText(s); this.textContent='Prompt copied'; }
catch(e){this.textContent='Use the copy icon below';}}</script>''',height=50)


@st.dialog('Send test',width='large')
def test_dialog(store,user,editor,key,cfg):
    from crm_resend_marketing import DeliveryError
    try:review_editor(store,user,editor,key+'dialog',cfg)
    except (ValueError,StoreUnavailable,DeliveryError,PermissionError) as exc:st.error(str(exc))
