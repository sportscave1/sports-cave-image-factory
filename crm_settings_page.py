"""Compact CRM settings host; old customer/segment routes and permissions survive."""
from table_design import TABLE_ROW_HEIGHT
from copy import deepcopy
from datetime import timedelta
import os
import uuid
import streamlit as st
import streamlit.components.v1 as components
import os_accounts
from crm_campaign_store import CampaignStore
from crm_campaign_content import new_document,render_campaign,settings
from crm_email_blocks import starter,STARTERS,PURPOSES
from crm_navigation import require
from crm_resend_marketing import get_resend_marketing_config_status
from crm_store import StoreUnavailable
from crm_logic import now

SECTIONS=('Customers','Segments','Templates','Reports','Email brand templates','Branding','Connections & Tracking','Prompts','Sending & Compliance')
PERMISSIONS={'Customers':'crm_customers_view','Segments':'crm_segments_view','Templates':'crm_templates_manage','Reports':'crm_reports_view'}


def campaign_settings_panel(shop,store,actions,navigate):
    """Secondary campaign surface; reuse existing permissions and setting writers."""
    require(actions.user,'crm_settings_view')
    with st.container(key='campaign-settings-panel'):
        st.markdown('#### Campaign Settings')
        st.html('<style>.st-key-campaign-settings-panel button{background:#fff!important;color:#222!important;border:1px solid #ddd!important;box-shadow:none!important}</style>')
        if os_accounts.is_admin(actions.user):
            try:
                records=CampaignStore(store.connect);sending=records.setting('sending')['value']
                delivery=get_resend_marketing_config_status()
                from crm_onsite import config
                st.table([{'Setting':name,'Value':value} for name,value in (
                    ('Marketing delivery','On' if delivery['marketing_enabled'] else 'Off · production sending unavailable'),
                    ('Smart Sending',str(sending['smart_hours'])+' hours'),
                    ('Website tracking','On' if config()['enabled'] else 'Off'),
                    ('Sender',delivery['sender'] or 'Not configured'),
                    ('Reply-To',delivery['reply_to'] or 'Not configured'))])
            except StoreUnavailable as exc:st.error(str(exc))
        settings_page(shop,store,actions,navigate,initial='Sending & Compliance',compact=True)


def settings_page(shop,store,actions,navigate,initial=None,compact=False):
    user=actions.user
    allowed=[name for name in SECTIONS if os_accounts.is_admin(user) or (name in PERMISSIONS and os_accounts.can_access_page(user,PERMISSIONS[name]))]
    if not allowed:st.info('Ask an administrator for access to campaign settings.');return
    if initial in allowed and st.session_state.get('crm_settings_alias')!=initial:
        st.session_state['crm_settings_section']=initial;st.session_state['crm_settings_alias']=initial
    if st.session_state.get('crm_settings_section') not in allowed:st.session_state['crm_settings_section']=allowed[0]
    section=st.selectbox('Campaign Settings',allowed,key='crm_settings_section')
    if section in PERMISSIONS:require(user,PERMISSIONS[section])
    if section=='Customers':
        from crm_page import customers_page
        customers_page(shop,store,user,navigate);return
    if section=='Segments':
        from crm_page import segments_page
        segments_page(shop,store,actions);return
    records=CampaignStore(store.connect)
    if section=='Sending & Compliance' and not compact:
        from crm_delivery_panel import render_delivery_panel
        render_delivery_panel(user)
    try:
        if section=='Templates':templates_page(records,shop,user)
        elif section=='Reports':campaign_report(records,shop,user)
        elif section=='Branding':branding_page(records,user)
        elif section=='Email brand templates':
            from crm_brand_template_ui import brand_templates_settings
            brand_templates_settings(records,user)
        elif section=='Connections & Tracking':connections_page(records,shop)
        elif section=='Prompts':prompts_page(records,user)
        else:compliance_page(records,user)
    except StoreUnavailable as exc:st.error(str(exc))


def templates_page(store,shop,user):
    from crm_campaign_page import open_editor,block_editor,reset_widgets,dirty
    unsaved=bool(st.session_state.get('campaign_editor') and dirty(st.session_state['campaign_editor']))
    if unsaved:st.info('Save or discard the open campaign before starting another draft from a template.')
    st.caption('Versioned templates · campaigns keep an independent snapshot · no automatic seeding')
    with st.expander('Sports Cave starters'):
        cols=st.columns(3)
        for col,name in zip(cols,STARTERS):
            with col:
                doc=new_document();doc['blocks']=starter(name)
                st.markdown('**'+name+'**')
                components.html(render_campaign(doc,store.render_settings())['html'],height=120,scrolling=False)
                if st.button('Customize '+name):
                    st.session_state['crm_template_edit']={'id':None,'version':None,'name':name,'document':doc};reset_widgets();st.rerun()
    archived=st.checkbox('Show archived templates');rows=store.templates(archived)
    if rows:
        page=st.number_input('Template page',1,max(1,(len(rows)+5)//6),1)
        for offset in (0,3):
            cols=st.columns(3)
            for col,row in zip(cols,rows[(page-1)*6+offset:(page-1)*6+offset+3]):
                with col:
                    doc=store.template_document(row)
                    components.html(render_campaign(doc,store.render_settings())['html'],height=100,scrolling=False)
                    st.markdown('**'+row['name'].replace('*','')+'**');st.caption('v'+str(row['version'])+' · '+str(row['updated_at'])[:16])
                    if st.button('Preview / edit',key='template_edit_'+str(row['id']),disabled=archived):
                        st.session_state['crm_template_edit']={'id':row['id'],'version':row['version'],'name':row['name'],'document':doc};reset_widgets();st.rerun()
                    a,b,c=st.columns(3)
                    if a.button('Use',key='template_use_'+str(row['id']),disabled=not os_accounts.can_access_page(user,'crm_campaigns_manage') or archived or unsaved):
                        doc['template_ref']={'id':str(row['id']),'version':row['version'],'name':row['name']};doc['campaign_key']='sc_'+uuid.uuid4().hex
                        open_editor(store.save(user,row['name']+' — draft',doc));st.success('Draft created. Open Campaigns to continue.')
                    if b.button('Copy',key='template_copy_'+str(row['id'])):store.save_design(user,(row['name']+' — copy')[:150],doc);st.rerun()
                    if c.button('Archive',key='template_archive_'+str(row['id']),disabled=archived):store.archive_design(user,row['id'],row['version']);st.rerun()
    edit=st.session_state.get('crm_template_edit')
    if edit:
        left,right=st.columns([4,6]);key='template_'+st.session_state.setdefault('campaign_edit_key',str(uuid.uuid4()))
        with left:
            edit['name']=st.text_input('Template name',edit['name'],key=key+'name')
            c=edit['document']['content'];c['subject']=st.text_input('Template subject',c['subject'],key=key+'subject');c['preheader']=st.text_input('Template preheader',c['preheader'],key=key+'preheader')
            block_editor(shop,edit['document'],key)
            if st.button('Save template revision'):
                row=store.save_design(user,edit['name'],edit['document'],edit['id'],edit['version']);edit.update(id=row['id'],version=row['version']);st.success('Template revision saved. Existing campaign snapshots are unchanged.')
        with right:
            from crm_campaign_page import layout_preview
            layout_preview(edit['document'],store.render_settings(),key)


def branding_page(store,user):
    row=store.setting('branding');v=deepcopy(row['value']);left,right=st.columns([4,6])
    with left:
        with st.form('branding_settings'):
            v['logo']=st.text_input('Approved public logo URL (JPEG/PNG)',v['logo'])
            v['accent']=st.color_picker('Restrained brand accent',v['accent'])
            v['font']=st.selectbox('Email typography',('Arial','Georgia'),index=('Arial','Georgia').index(v['font']))
            v['button_style']=st.selectbox('Button style',('Solid black','Outlined black'),index=('Solid black','Outlined black').index(v['button_style']))
            st.caption('Email-safe fallbacks, strong-contrast buttons, warm white background and 16px body. Brand header and legal footer remain system-generated.')
            social=st.text_area('Confirmed social links (one per line)','\n'.join(v['social_links']),height=80)
            v['social_links']=[s.strip() for s in social.splitlines() if s.strip()]
            saved=st.form_submit_button('Save branding')
        if saved:store.save_setting(user,'branding',v,row['version']);st.success('Branding saved.');st.rerun()
    with right:
        doc=new_document();doc['blocks']=starter('Collector Note')
        components.html(render_campaign(doc,{**store.render_settings(),**v})['html'],width=600,height=430,scrolling=True)
    st.caption('The text Sports Cave header is used until an approved logo is configured. Legal identity belongs in Sending & Compliance.')


def prompts_page(store,user):
    row=store.setting('prompts');values=deepcopy(row['value'])
    purpose=st.selectbox('Prompt guidance',('default',*PURPOSES))
    text=st.text_area('Versioned brand guidance',values.get(purpose,''),height=170,key='prompt_guidance_'+purpose+str(row['version']))
    st.caption('Guidance is subordinate to the locked facts and compliance rules. No AI API is connected; responses must pass the versioned JSON validator before selected fields can be applied.')
    if st.button('Save prompt guidance'):values[purpose]=text;store.save_setting(user,'prompts',values,row['version']);st.success('Prompt revision saved.');st.rerun()
    with st.expander('Prompt versions'):
        st.dataframe(store.q("SELECT version,actor,created_at FROM crm_settings_history WHERE key='prompts' ORDER BY version DESC LIMIT 30"),hide_index=True, row_height=TABLE_ROW_HEIGHT)


def compliance_page(store,user):
    row=store.setting('compliance');v=deepcopy(row['value']);send=store.setting('sending');s=deepcopy(send['value'])
    with st.expander('Business identity + locked footer',expanded=True):
        with st.form('compliance_settings'):
            a,b=st.columns(2)
            v['business']=a.text_input('Business / legal display name',v['business'])
            v['contact']=a.text_input('Business contact email',v['contact'])
            v['website']=b.text_input('Website',v['website']);v['privacy']=b.text_input('Confirmed privacy-policy URL',v['privacy'])
            v['identity_confirmed']=b.checkbox('Nathan confirmed this contact identity',v['identity_confirmed'])
            saved=st.form_submit_button('Save compliance details')
        if saved:store.save_setting(user,'compliance',v,row['version']);st.success('Business details saved.');st.rerun()
    with st.expander('Sending frequency',expanded=True):
        with st.form('internal_settings'):
            s['smart_hours']=int(st.number_input('Default Smart Sending hours',1,168,s['smart_hours']))
            saved=st.form_submit_button('Save sending frequency')
        if saved:store.save_setting(user,'sending',s,send['version']);st.success('Sending frequency saved.');st.rerun()
        st.caption('Campaign tests accept one manually entered email address from an administrator. Production marketing controls are not editable here.')
    with st.expander('Manual suppression for support unsubscribe requests'):
        with st.form('manual_suppression'):
            address=st.text_input('Mailbox to suppress')
            confirmed=st.checkbox('Confirm this unsubscribe / suppression request')
            clicked=st.form_submit_button('Suppress marketing locally')
        if clicked:
            if not confirmed:st.warning('Confirm the request first.')
            else:store.manual_suppression(user,address);st.success('Suppressed locally immediately. Shopify consent was not changed.')
        st.caption('Local suppression is never removed automatically. Provider / Shopify reconciliation remains pending and cannot make an address eligible again.')
    st.info('Production readiness: blocked. RFC 8058 / visible unsubscribe, domain evidence, DMARC, webhook proof, legal review and a separately approved transport are required. No jurisdiction receives automatic legal clearance.')


def connections_page(store,shop):
    from crm_onsite import config,pixel_code
    from crm_campaign_page import copy_prompt
    from shopify_sync import get_config
    delivery=get_resend_marketing_config_status();cfg=config()
    shop_configured=bool(shop.transport) or get_config()['configured']
    if st.button('Check Shopify connection and read scopes'):
        try:
            proof=shop.campaign_connection();proof['checked_at']=now().isoformat()
        except Exception:
            proof={'connected':False,'scopes':[],'checked_at':now().isoformat()}
        st.session_state['crm_shopify_connection_proof']=proof
    proof=st.session_state.get('crm_shopify_connection_proof',{})
    shop_evidence=('Tested read connection · '+proof['checked_at']) if proof.get('connected') else 'Connection unavailable — check permissions / credentials' if proof else 'Configured only; not tested in this session'
    latest=store.q('SELECT max(received_at) AS at FROM crm_delivery_events WHERE test_id IS NOT NULL OR send_id IS NOT NULL',one=True)['at']
    tests=store.q("SELECT max(accepted_at) AS at FROM crm_internal_tests WHERE status='ACCEPTED'",one=True)['at']
    st.dataframe([
        {'Connection':'Shopify','Configured':'Configured' if shop_configured else 'Missing','Evidence':shop_evidence},
        {'Connection':'Resend marketing API','Configured':'Yes' if delivery['configured'] else 'Missing','Evidence':'Accepted internal test: '+str(tests or 'Not tested')},
        {'Connection':'CRM webhook signature','Configured':'Yes' if os.getenv('CRM_RESEND_WEBHOOK_SECRET') else 'Missing','Evidence':'Latest mapped verified event: '+str(latest or 'Not receiving verified events')},
        {'Connection':'Campaign URL tracking','Configured':'Deterministic UTMs','Evidence':'Internal test context excluded from revenue'},
        {'Connection':'VentraIP support mailbox','Configured':'Existing Email page','Evidence':'Reference only — unchanged'},
    ],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
    if proof.get('connected'):
        scopes=set(proof['scopes'])
        st.caption('Reported scopes: '+(', '.join(sorted(scopes)) or 'None reported'))
        missing=[s for s in ('read_customers','read_products','read_orders') if s not in scopes and s.replace('read_','write_') not in scopes]
        if missing:st.warning('Missing permission: '+', '.join(missing)+'. Ask for a separate scope review; no permissions were expanded.')
        st.caption('Scope presence does not prove access to protected customer data, historical orders or every journey/image field. Those reads remain explicit and fail safely.')
    st.code((os.getenv('CRM_PUBLIC_BASE_URL') or '<configured HTTPS webhook base>').rstrip('/')+'/webhooks/resend/crm',language=None)
    st.caption('Register only after approval, with its own CRM_RESEND_WEBHOOK_SECRET. Request email.sent, delivered, delivery_delayed, failed, bounced, complained, opened and clicked. Configuration presence does not prove permissions or delivery.')
    st.markdown('**Onsite tracking**')
    last=store.q('SELECT event_type,occurred_at,received_at,test_context FROM crm_website_events ORDER BY received_at DESC LIMIT 12')
    status='Disabled' if not cfg['enabled'] else 'Setup required' if not cfg['configured'] else 'Receiving events' if last else 'Awaiting consent / first event — not yet verified'
    st.info(status)
    st.caption('Last event: '+(str(last[0]['received_at']) if last else 'None received')+' · Browser events are untrusted, do not identify customers and never prove payment.')
    with st.expander('Installation + test instructions'):
        st.write('After separate approval: configure CRM_PUBLIC_BASE_URL, CRM_WEBSITE_PIXEL_ID (public random identifier), CRM_WEBSITE_ALLOWED_ORIGINS and CRM_WEBSITE_TRACKING_ENABLED. Use the existing webhook service. In Shopify → Settings → Customer events, add a custom pixel requiring both Analytics and Marketing permission. Keep its test context enabled for verification. No installation is performed here.')
        st.write('Generated code starts disabled. Test denied consent (no requests), granted consent (one bounded event), withdrawal (requests stop and session context clears), preflight/CORS and all five standard events. Add an observed sandbox Origin only after review; a null origin, if required by the actual Shopify sandbox, grants no authentication. See the runbook before approval.')
        if cfg['configured']:
            source=pixel_code(cfg);copy_prompt(source);st.code(source,language='javascript')
        else:st.caption('Setup required before code generation: public pixel ID, allowed origins and HTTPS webhook base.')
    if last:
        with st.expander('Event debug (no personal data)'):st.dataframe(last,hide_index=True, row_height=TABLE_ROW_HEIGHT)


def campaign_report(store,shop,user,identity=None):
    require(user,'crm_reports_view')
    st.markdown('**Campaign reports**')
    report=store.delivery_report(identity);totals=report['counts'];events=report['events']
    st.caption('INTERNAL TEST DATA · accepted is not delivered · clicks may include scanners; opens may reflect privacy/proxy activity')
    cols=st.columns(4)
    for col,label,value in zip(cols,('Attempted','Accepted','Delivered','Failed / bounced'),(totals['total'],totals['accepted'],events.get('email.delivered','Awaiting events'),str(totals['failed'])+' / '+str(events.get('email.bounced','—')))):col.metric(label,value)
    st.caption('Unique clicked messages: '+str(events.get('email.clicked','—'))+' · Opened: '+str(events.get('email.opened','—'))+' · Complaints: '+str(events.get('email.complained','—'))+' · Unsubscribe: inactive for internal tests')
    if report['tests']:st.dataframe([{k:r[k] for k in ('campaign_version','status','provider_id','created_at','delivered')} for r in report['tests']],hide_index=True,height=180, row_height=TABLE_ROW_HEIGHT)
    st.caption('PRODUCTION DATA · Live campaigns are not activated. Internal tests and website test events are excluded.')
    with st.expander('Existing campaign / flow history'):
        summary,campaigns,flows=store.reports()
        st.dataframe([summary],hide_index=True, row_height=TABLE_ROW_HEIGHT)
        st.caption('Historical OS marketing receipts and verified events only. Counts do not prove current provider connectivity. Opens are a secondary signal; clicks can include scanners.')
        if campaigns:st.dataframe(campaigns,hide_index=True, row_height=TABLE_ROW_HEIGHT)
        if flows:st.dataframe(flows,hide_index=True, row_height=TABLE_ROW_HEIGHT)
    if not identity:
        candidates=store.list_drafts()
        if candidates:
            row=st.selectbox('Campaign report',candidates,format_func=lambda r:r['name'])
            if st.button('Open campaign report'):st.session_state['crm_report_campaign']=row['id']
        identity=st.session_state.get('crm_report_campaign')
    if identity:
        row=store.draft(identity);key='report_'+str(identity)
        st.markdown('**'+row['name'].replace('*','')+'**')
        web=store.q('SELECT event_type,count(*) AS events FROM crm_website_events WHERE campaign_key=%s AND test_context=false GROUP BY event_type',(row['document'].get('campaign_key',''),))
        st.caption('Website events: '+('No production observations' if not web else str(web)))
        st.caption('Orders associated with the last recorded Shopify campaign visit within 30 days. This is an association, not incremental revenue. Pixel checkout events are never revenue evidence.')
        cols=st.columns(2);start=cols[0].date_input('Order dates from (UTC)',now().date()-timedelta(days=30),key=key+'start');end=cols[1].date_input('Through (UTC)',now().date(),key=key+'end')
        state=st.session_state.get(key+'attribution',store.state(key+'attribution'))
        if state and (state.get('start')!=start.isoformat() or state.get('end')!=end.isoformat()):state={}
        refresh=st.button('Read Shopify attribution',key=key+'refresh')
        more=st.button('Continue order pages',key=key+'more',disabled=not state.get('cursor'))
        if refresh or more:
            from crm_attribution import refresh_page
            if start>end:raise ValueError('Choose a valid order date range.')
            pending={'complete':False,'start':start.isoformat(),'end':end.isoformat(),'checked_at':now().isoformat()}
            st.session_state[key+'attribution']=pending;store.set_state(key+'attribution',pending)
            result=refresh_page(store,shop,row,start.isoformat(),(end+timedelta(days=1)).isoformat(),state.get('cursor') if more else None)
            result['reasons']={k:result['reasons'].get(k,0)+(state.get('reasons',{}).get(k,0) if more else 0) for k in set(result['reasons'])|set(state.get('reasons',{}))}
            result.update(start=start.isoformat(),end=end.isoformat(),checked_at=now().isoformat());st.session_state[key+'attribution']=result;store.set_state(key+'attribution',result);st.rerun()
        if not state or not state.get('complete'):st.info('Shopify-associated revenue unavailable / incomplete. Explicitly read every page; missing permissions and pending journey data are not zero revenue.')
        elif state['reasons'].get('journey_unavailable') or state['reasons'].get('revenue_unavailable'):st.warning('Attribution data incomplete: some Shopify journeys or revenue fields are unavailable. Totals withheld.');st.json(state)
        else:
            totals=store.q('SELECT currency,count(*) AS associated_orders,sum(amount) AS net_payments FROM crm_order_attribution WHERE campaign_id=%s AND eligible=true AND order_created_at>=%s AND order_created_at<%s GROUP BY currency',(identity,start.isoformat(),(end+timedelta(days=1)).isoformat()))
            st.dataframe(totals,hide_index=True, row_height=TABLE_ROW_HEIGHT)
            st.caption('Shopify netPaymentSet.shopMoney: received payments minus refunds, grouped by currency; paid, non-test, non-canceled orders only. Refresh to reflect later refunds and cancellations. No currency conversion. Last checked: '+state['checked_at'])
