"""Lazy CRM pages. Shopify owns all customer data; only configuration is editable."""
from table_design import TABLE_ROW_HEIGHT
import json
import uuid
from datetime import timedelta
import streamlit as st
from crm_navigation import PAGE_KEYS,LABELS,require
from crm_logic import SPORTS,consent,now,date,LiveFacts,matches,rule,eligibility,recipient_hash
from crm_cache import CACHE
from crm_shopify import Shopify,CapabilityUnavailable,gid
from crm_store import Store,StoreUnavailable
from crm_service import Actions
from crm_resend import Config,MarketingDisabled
from crm_templates import render,FIELDS


def records(customers):
    return [{'Customer':(' '.join(filter(None,[c.get('firstName'),c.get('lastName')])) or c.get('email') or 'Customer'),
      'Email':c.get('email',''),'Country':(c.get('defaultAddress') or {}).get('countryCodeV2','—'),
      'Consent':consent(c),'Orders':int(c.get('numberOfOrders',0)),
      'Lifetime value':c.get('amountSpent',{}).get('amount','0')+' '+c.get('amountSpent',{}).get('currencyCode',''),
      'Last order':(c.get('lastOrder') or {}).get('createdAt','—')[:10],
      'Interests':'View profile','Segments':'View profile'} for c in customers]


def paging(page,key):
    left,_,right=st.columns([1,5,1])
    if left.button('First page',key=key+'_first',disabled=not st.session_state.get(key)):
        st.session_state[key]=None;st.rerun()
    if right.button('Next page',key=key+'_next',disabled=not page.get('pageInfo',{}).get('hasNextPage')):
        st.session_state[key]=page['pageInfo']['endCursor'];st.rerun()


def table(customers,key='crm_customers_table'):
    if not customers:st.caption('No customers in this page.');return None
    event=st.dataframe(records(customers),hide_index=True,use_container_width=True,on_select='rerun',selection_mode='single-row',key=key,height=440, row_height=TABLE_ROW_HEIGHT)
    rows=event.selection.rows
    return customers[rows[0]]['id'] if rows and rows[0]<len(customers) else None


def available(call):
    try:return call()
    except (CapabilityUnavailable,StoreUnavailable,ValueError) as exc:st.caption(str(exc));return None


def profile(shop,store,customer_id,navigate,user):
    c=shop.customer(customer_id)
    if not c:st.info('This customer is no longer available in Shopify.');return
    st.divider();st.subheader(' '.join(filter(None,[c.get('firstName'),c.get('lastName')])) or 'Customer')
    st.caption(str(c.get('email') or 'No email')+' · '+customer_id)
    cols=st.columns(5)
    count=int(c.get('numberOfOrders') or 0);amount=float(c.get('amountSpent',{}).get('amount',0))
    currency=(c.get('amountSpent') or {}).get('currencyCode','')
    for col,label,value in zip(cols,['Consent','Orders','Lifetime value','Average order','Country'],[consent(c),count,f'{amount:,.2f} {currency}',f'{amount/count:,.2f} {currency}' if count else '—',(c.get('defaultAddress') or {}).get('countryCodeV2','—')]):col.metric(label,value)
    first=available(lambda:shop.first_order(customer_id))
    st.caption('Consent updated: '+str((c.get('emailMarketingConsent') or {}).get('consentUpdatedAt') or '—')+' · First order: '+str((first or {}).get('createdAt','—'))[:10]+' · Last order: '+str((c.get('lastOrder') or {}).get('createdAt','—'))[:10])
    with st.expander('Purchase history',expanded=True):
        key='crm_orders_'+customer_id;page=shop.orders(customer_id,st.session_state.get(key))
        st.dataframe([{'Order':o['name'],'Date':o['createdAt'][:10],'Payment':o['displayFinancialStatus'],'Value':o['totalPriceSet']['shopMoney']['amount'],
          'Products':', '.join(n['title']+(' · '+n['variantTitle'] if n.get('variantTitle') else '')+' × '+str(n['quantity']) for n in o['lineItems']['nodes'])} for o in page['nodes']],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
        paging(page,key)
        detailed=[o for o in page['nodes'] if o['lineItems']['pageInfo'].get('hasNextPage')]
        if detailed:
            order=st.selectbox('More line items',detailed,format_func=lambda o:o['name'],key=key+'_line_order')
            line_key='crm_lines_'+order['id']
            lines=shop.line_page('order',order['id'],st.session_state.get(line_key))
            st.dataframe([{'Product':n['title'],'Variant':n.get('variantTitle'),'Quantity':n['quantity']} for n in lines['nodes']],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
            paging(lines,line_key)
    with st.expander('Interests & owned editions'):
        st.caption('Derived from actual product tags, categories and collections in live purchase history.')
        if st.button('Load interests and editions',key='facts_'+customer_id):
            facts=available(lambda:LiveFacts(shop,c,store.editions).purchases())
            if facts:st.write(' · '.join(sorted(facts['interest'])) or 'No supported sport categories found.')
            editions=available(lambda:store.editions(customer_id,c.get('email','')))
            if editions is not None:st.dataframe(editions,hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
    with st.expander('Segments'):
        if st.button('Check segment membership',key='membership_'+customer_id):
            # Native membership query, one batch; no persisted customer memberships.
            segments=shop.segments()['nodes']
            members=available(lambda:shop.memberships(customer_id,[x['id'] for x in segments]))
            if members is not None:st.write(', '.join(s['name'] for s in segments if s['id'] in members) or 'No match in this segment page.')
            st.caption('First 50 Shopify segments. Open Segments for the remaining pages.')
    with st.expander('Automation history & campaign activity'):
        history=available(lambda:store.history(customer_id))
        if history is not None:st.dataframe(history,hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
    import os_accounts
    if os_accounts.can_access_page(user,'Email') and st.button('Open in Email',key='support_'+customer_id):navigate('Email')


def customers_page(shop,store,user,navigate):
    cols=st.columns(5)
    queries=[None,"email_subscription_status = 'SUBSCRIBED'",'number_of_orders >= 2',f"customer_added_date >= { (now()-timedelta(days=30)).date() }"]
    for col,label,query in zip(cols,['Total Customers','Subscribed','Repeat Buyers','Customers 30 Days'],queries):
        try:col.metric(label,shop.count(query))
        except CapabilityUnavailable:col.metric(label,'—')
    cols[4].metric('Lifetime Revenue','—',help='Store-wide lifetime aggregation is not scanned on page load. Individual Shopify lifetime values appear below.')
    native_segments=available(lambda:shop.segments()) or {'nodes':[]}
    with st.form('crm_customer_search'):
        query=st.text_input('Search customers',placeholder='Name, email or Shopify customer ID')
        a,b,c,d,e=st.columns(5)
        state=a.selectbox('Consent',['Any','SUBSCRIBED','UNSUBSCRIBED','PENDING','NOT_SUBSCRIBED'])
        country=b.selectbox('Country',['Any','AU','US','GB'])
        orders=c.selectbox('Orders',['Any','At least 1','Repeat buyers'])
        last=d.selectbox('Last purchase',['Any','Last 30 days','180+ days'])
        interest=e.selectbox('Interest',['Any',*SPORTS])
        segment=st.selectbox('Segment',['All customers',*native_segments['nodes']],format_func=lambda x:x if isinstance(x,str) else x['name'])
        submit=st.form_submit_button('Search')
    if submit:
        st.session_state['crm_customer_segment']=segment['id'] if isinstance(segment,dict) else None
        st.session_state['crm_customer_filters']=(query,state,country,orders,last,interest);st.session_state['crm_customer_cursor']=None
    query,state,country,orders,last,interest=st.session_state.get('crm_customer_filters',('', 'Any','Any','Any','Any','Any'))
    terms=[]
    if query.strip():
        identity=gid(query.strip())
        terms.append('id:'+identity.rsplit('/',1)[-1] if identity else json.dumps(query.strip()))
    if state=='SUBSCRIBED':terms.append('accepts_marketing:true')
    if country!='Any':terms.append('country:'+country)
    if orders!='Any':terms.append('orders_count:>='+('2' if orders=='Repeat buyers' else '1'))
    if last=='Last 30 days':terms.append('order_date:>='+str((now()-timedelta(days=30)).date()))
    if last=='180+ days':terms.append('orders_count:>=1 AND NOT order_date:>='+str((now()-timedelta(days=180)).date()))
    selected_segment=st.session_state.get('crm_customer_segment')
    if selected_segment:
        page=shop.members(selected_segment,after=st.session_state.get('crm_customer_cursor'))
        st.caption('Filters apply to this live segment page. Continue paging for further matches.')
    else:page=shop.customers(st.session_state.get('crm_customer_cursor'),' AND '.join(terms) or None)
    rows=page['nodes']
    if selected_segment and query.strip():rows=[c for c in rows if query.casefold().strip() in (' '.join(str(c.get(k) or '') for k in ('firstName','lastName','email','id'))).casefold()]
    if country!='Any':rows=[c for c in rows if (c.get('defaultAddress') or {}).get('countryCodeV2')==country]
    if orders!='Any':rows=[c for c in rows if int(c.get('numberOfOrders',0)) >= (2 if orders=='Repeat buyers' else 1)]
    if state!='Any':rows=[c for c in rows if consent(c)==state]
    if last!='Any':rows=[c for c in rows if matches(rule('last_order_days',30 if last=='Last 30 days' else 180,'lte' if last=='Last 30 days' else 'gte'),LiveFacts(shop,c))]
    if interest!='Any':
        rows=[c for c in rows if matches(rule('interest',interest,'contains'),LiveFacts(shop,c,store.editions))]
        st.caption('Interest evaluated from purchases for this Shopify page. Continue paging for further matches.')
    selected=table(rows,key='crm_customer_table_'+str(st.session_state.get('crm_customer_cursor')))
    paging(page,'crm_customer_cursor')
    if selected:profile(shop,store,selected,navigate,user)
    st.caption('Shopify display data checked at '+now().strftime('%H:%M:%S UTC')+' · Refresh bypasses the display cache.')


def audience_count(shop,store,source,key):
    from crm_audience import count_page
    import hashlib
    identity=hashlib.sha256(json.dumps(source,sort_keys=True,default=str).encode()).hexdigest()
    state=st.session_state.get(key)
    if state and state['identity']!=identity:state=None
    label='Continue counting' if state and not state['result']['complete'] else 'Count eligible audience'
    if st.button(label,key=key+'_button'):
        previous=state['result'] if state and not state['result']['complete'] else None
        with st.spinner('Checking the next live customer page…'):
            result=count_page(shop,store,source,previous)
        state={'identity':identity,'result':result};st.session_state[key]=state
    if state:
        result=state['result']
        st.caption(f"{result['eligible']} eligible unique addresses · {result['members']} members · "+('count complete' if result['complete'] else f"partial count, {result['scanned']} customers checked"))
        st.caption('Live Shopify consent and Sports Cave suppressions checked. Resend suppression is checked again before every send; this count can decrease. Counts stay in session memory only.')


def segments_page(shop,store,actions):
    st.caption('Shopify owns segment membership. Sports Cave stores rule definitions only.')
    native=available(lambda:shop.segments(st.session_state.get('crm_segment_cursor')))
    if native:
        st.dataframe([{'Segment':s['name'],'Source':'Shopify','Updated':s['lastEditDate'],'Customers':'Open segment','Eligible':'Preview'} for s in native['nodes']],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
        if native['nodes']:
            chosen=st.selectbox('Shopify segment',native['nodes'],format_func=lambda s:s['name'])
            preview_key='crm_native_preview_'+chosen['id']
            with st.expander('Live segment preview',expanded=bool(st.session_state.get(preview_key))):
                if st.button('Load current members'):st.session_state[preview_key]=True
                if st.session_state.get(preview_key):
                    member_key='crm_member_cursor_'+chosen['id']
                    page=shop.members(chosen['id'],after=st.session_state.get(member_key));st.code(chosen['query'],language=None)
                    st.caption(f"{page['totalCount']} live members · {sum(consent(c)=='SUBSCRIBED' for c in page['nodes'])} subscribed in this 50-customer sample. Suppressions are rechecked before delivery.")
                    table(page['nodes'],'native_members_'+str(st.session_state.get(member_key)))
                    paging(page,member_key)
                    audience_count(shop,store,('Shopify',chosen),'crm_native_count')
        paging(native,'crm_segment_cursor')
    definitions=available(lambda:store.list('segments'))
    if definitions is None:return
    st.subheader('Sports Cave definitions')
    choice=st.selectbox('Definition',['New definition',*definitions],format_func=lambda x:x if isinstance(x,str) else x['name'])
    existing=choice if isinstance(choice,dict) else {}
    mode=st.radio('Rule editor',['Simple','AND / OR rules'],horizontal=True,index=1 if existing else 0)
    with st.form('crm_segment_editor'):
        name=st.text_input('Name',existing.get('name',''))
        if mode=='Simple':
            from crm_logic import FIELDS
            field=st.selectbox('Field',sorted(FIELDS));op=st.selectbox('Comparison',['eq','gte','lte','contains']);value=st.text_input('Value')
            rules=rule(field,value,op)
        else:
            raw=st.text_area('Rules (JSON)',json.dumps(existing.get('rules',rule('consent','SUBSCRIBED')),indent=2),height=150)
            rules=None
        save=st.form_submit_button('Save definition')
        preview=st.form_submit_button('Preview live matches')
    if save or preview:
        if rules is None:rules=json.loads(raw)
        if save:actions.segment(name,rules,existing.get('id'));st.success('Definition saved.');st.rerun()
        else:
            page=shop.customers();matched=[c for c in page['nodes'] if matches(rules,LiveFacts(shop,c,store.editions))]
            st.caption(f'{len(matched)} matches among {len(page["nodes"])} current customers. Membership is evaluated live, not saved.');table(matched,'custom_preview')


def template_editor(row,key):
    content=dict(row['content'])
    name=st.text_input('Template name',row['name'],key=key+'_name')
    for field,label in [('subject','Subject'),('preview','Preview text'),('headline','Headline')]:content[field]=st.text_input(label,content[field],key=key+'_'+field)
    content['body']=st.text_area('Body',content['body'],height=140,key=key+'_body')
    a,b=st.columns([1,2]);content['cta_label']=a.text_input('CTA label',content['cta_label'],key=key+'_cta_label');content['cta_url']=b.text_input('CTA URL',content['cta_url'],key=key+'_cta_url')
    content['product_block']=st.checkbox('Product block',content['product_block'],key=key+'_products')
    content['footer']=st.text_input('Marketing footer',content['footer'],key=key+'_footer')
    st.caption('Placeholders: {{first_name}}, {{checkout_url}}, {{order_name}}, {{store_url}}. Support signatures are separate.')
    return name,content


def preview_template(content,config):
    import streamlit.components.v1 as components
    sample=render(content,{'first_name':'Alex','store_url':'https://www.sportscaveshop.com','checkout_url':'https://www.sportscaveshop.com','order_name':'#SC Preview',
      'products':[{'title':'Collector edition sports art','quantity':1,'price':'249.00'}]},'https://example.com/unsubscribe',config.logo_url,'preview')
    # Previews embed the official asset locally; outgoing delivery uses its public URL.
    import base64
    from pathlib import Path
    logo=Path(__file__).parent/'static/branding/sports-cave-os-icon-192-v2.png'
    if logo.is_file():sample['html']=sample['html'].replace(config.logo_url,'data:image/png;base64,'+base64.b64encode(logo.read_bytes()).decode())
    tab1,tab2=st.tabs(['HTML preview','Plain text'])
    with tab1:components.html(sample['html'],height=550,scrolling=True)
    with tab2:st.text(sample['text'])


def templates_page(store,actions):
    rows=store.list('templates')
    if not rows:st.info('Initialize the draft library from Automations.');return
    row=st.selectbox('Template',rows,format_func=lambda r:r['name'])
    left,right=st.columns([1,1])
    with left:
        with st.form('crm_template_edit_'+str(row['id'])):
            name,content=template_editor(row,str(row['id']))
            save=st.form_submit_button('Save template');preview=st.form_submit_button('Preview')
        if save:actions.template(row,name,content);st.success('New template version saved.');st.rerun()
    with right:preview_template(content,actions.config)


def automation_workspace(shop,store,actions,navigate=lambda _:None):
    """Route-specific boundary; control-flow BaseExceptions still reach Streamlit."""
    try:
        from crm_automation_ui import workspace
        workspace(shop,store,actions,navigate=navigate)
    except Exception as exc:
        __import__('logging').getLogger(__name__).error('automation_render failure=%s',type(exc).__name__)
        st.error('Automations temporarily unavailable. Other OS sections remain available.')


def automations_page(store,actions,shop=None):
    automation_workspace(shop,store,actions)


def campaigns_page(shop,store,actions):
    templates=[t for t in store.list('templates') if t['kind']=='Campaign'];definitions=store.list('segments')
    if not templates:st.info('Initialize templates from Automations first.');return
    native=available(lambda:shop.segments())
    sources=[('Shopify',s) for s in (native or {}).get('nodes',[])]+[('Sports Cave',s) for s in definitions]
    if not sources:st.info('No available segment definitions.');return
    source=st.selectbox('Audience',sources,format_func=lambda x:x[0]+' · '+x[1]['name'])
    audience_count(shop,store,source,'crm_campaign_count')
    if st.button('Preview current audience'):
        page=shop.members(source[1]['id']) if source[0]=='Shopify' else shop.customers()
        rows=page['nodes'] if source[0]=='Shopify' else [c for c in page['nodes'] if matches(source[1]['rules'],LiveFacts(shop,c,store.editions))]
        ready=[c for c in rows if eligibility(c,store.suppressed(c['id'],recipient_hash(c.get('email'))))[0]]
        st.caption(f'{len(ready)} locally eligible in this live sample. Full IDs resolve at send time; Shopify and provider suppression are rechecked individually.')
        table(ready,'campaign_preview')
    template=st.selectbox('Campaign template',templates,format_func=lambda r:r['name'])
    with st.expander('Edit content & preview'):
        import os_accounts
        if os_accounts.can_access_page(actions.user,'CRM Templates'):
            with st.form('campaign_content_'+str(template['id'])):
                name,content=template_editor(template,'campaign_'+str(template['id']))
                if st.form_submit_button('Save content version'):actions.template(template,name,content);st.rerun()
            preview_template(content,actions.config)
        else:preview_template(template['content'],actions.config)
    with st.form('new_campaign'):
        name=st.text_input('Campaign name')
        if st.form_submit_button('Save campaign draft'):
            actions.campaign(name,template,source[1]['id'] if source[0]=='Shopify' else None,source[1]['id'] if source[0]=='Sports Cave' else None);st.success('Campaign draft saved.');st.rerun()
    st.session_state.setdefault('crm_test_operation',str(uuid.uuid4()))
    with st.form('crm_test_send'):
        address=st.text_input('Explicit test recipient')
        test=st.form_submit_button('Send test',disabled=not actions.config.tests_enabled)
    if test:
        actions.test(template,address,st.session_state['crm_test_operation']);st.success('Test queued once.');st.session_state['crm_test_operation']=str(uuid.uuid4())
    rows=store.list('campaigns')
    if rows:
        st.dataframe([{'Campaign':r['name'],'Status':r['status'],'Scheduled':str(r.get('scheduled_at') or '—')} for r in rows],hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
        row=st.selectbox('Saved campaign',rows,format_func=lambda r:r['name'])
        with st.expander('Saved campaign content'):
            st.caption('Pinned template version '+str(row['template_version'])+'. Later library edits do not change this campaign.')
            preview_template(store.template(row['template_id'],row['template_version']),actions.config)
        a,b,c=st.columns(3)
        day=a.date_input('Send date',now().date());clock=b.time_input('Send time (UTC)',(now()+timedelta(hours=1)).time())
        if c.button('Schedule',disabled=not actions.config.enabled or row['status']!='DRAFT'):
            import datetime
            actions.schedule(row,datetime.datetime.combine(day,clock,tzinfo=datetime.timezone.utc));st.rerun()
        if st.button('Send campaign',disabled=not actions.config.enabled or row['status']!='DRAFT'):
            actions.schedule(row,now()+timedelta(seconds=1));st.rerun()
        if st.button('Pause campaign',disabled=row['status'] in ('DRAFT','SENT','CANCELLED','PAUSED')):actions.pause(row);st.rerun()
        if row['status']=='PAUSED' and st.button('Resume campaign',disabled=not actions.config.enabled):actions.resume(row);st.rerun()
    st.caption('Production send and scheduling are disabled until reviewed configuration is enabled. No Klaviyo flows are changed.')


def reports_page(store):
    summary,campaigns,automations=store.reports();cols=st.columns(7)
    metrics=[('Sends',summary['sends']),('Delivered',summary['delivered']),('Open rate',f"{summary['opened']/summary['delivered']:.1%}" if summary['delivered'] else '—'),('Click rate',f"{summary['clicked']/summary['delivered']:.1%}" if summary['delivered'] else '—'),('Bounces',summary['bounces']),('Complaints',summary['complaints']),('Unsubscribes',summary['unsubscribes'])]
    for col,(label,value) in zip(cols,metrics):col.metric(label,value)
    st.caption('Opens/clicks reflect Resend events and can include email-client privacy activity. Attributed revenue: —. Recovery is not proof of causation.')
    st.subheader('Automations');st.dataframe(automations,hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
    st.subheader('Campaigns');st.dataframe(campaigns,hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
    st.caption('Worker: '+str(store.state('worker_health').get('checked_at') or 'Not started'))
    held=store.q("SELECT status,error_code,created_at FROM crm_marketing_sends WHERE status IN ('FAILED','UNCERTAIN','BLOCKED') ORDER BY created_at DESC LIMIT 50")
    if held:
        with st.expander('Held or excluded deliveries'):
            st.dataframe(held,hide_index=True,use_container_width=True, row_height=TABLE_ROW_HEIGHT)
            st.caption('Uncertain submissions are never retried automatically. Check the provider receipt before any manual follow-up.')


def _render_page(route,user,navigate=lambda _:None,*,shop=None,store=None,config=None,loading=None):
    require(user,PAGE_KEYS[route])
    shop=shop or Shopify();store=store or Store();actions=Actions(store,user,config)
    if route=='CRM Campaigns':
        from crm_campaign_page import campaign_workspace
        from crm_resend_marketing import DeliveryError
        try: campaign_workspace(shop,store,actions,navigate)
        except (CapabilityUnavailable,StoreUnavailable,MarketingDisabled,DeliveryError,PermissionError,ValueError) as exc: st.warning(str(exc))
        return
    if route=='CRM Automations':
        automation_workspace(shop,store,actions,navigate=navigate)
        return
    left,right=st.columns([9,1])
    left.markdown('### EMAIL · '+('CAMPAIGN SETTINGS' if route=='CRM Settings' else LABELS[route].upper()))
    left.caption('Shopify is the live source · display cache up to 90 seconds · marketing delivery '+('enabled' if actions.config.enabled else 'disabled'))
    if loading:loading.empty()
    if right.button('Refresh',key='crm_refresh'):CACHE.invalidate();st.rerun()
    import os_accounts
    from crm_navigation import SETTINGS_ALIASES
    if route=='CRM Settings' or route in SETTINGS_ALIASES:
        if os_accounts.can_access_page(user,'crm_campaigns_manage') and st.button('Back to campaigns',type='tertiary'):
            navigate('CRM Campaigns')
        from crm_settings_page import settings_page
        try:settings_page(shop,store,actions,navigate,SETTINGS_ALIASES.get(route))
        except (CapabilityUnavailable,StoreUnavailable,MarketingDisabled,PermissionError,ValueError) as exc:st.warning(str(exc))
        return
    try:
        version=store.state('cache_version').get('version')
        if version:CACHE.invalidate(version)
    except StoreUnavailable as exc:
        if route not in ('CRM Customers','CRM Segments'):
            st.error(str(exc))
            if route=='CRM Automations':
                st.caption('Automations · existing workflows will return when persistence is restored. OS flow activation remains disabled.')
                st.button('Initialize draft library',disabled=True)
            return
    try:
        if route=='CRM Customers':customers_page(shop,store,user,navigate)
        elif route=='CRM Segments':segments_page(shop,store,actions)
        elif route=='CRM Automations':automations_page(store,actions,shop)
        elif route=='CRM Campaigns':campaigns_page(shop,store,actions)
        elif route=='CRM Templates':templates_page(store,actions)
        elif route=='CRM Reports':reports_page(store)
    except (CapabilityUnavailable,StoreUnavailable,MarketingDisabled,PermissionError,ValueError) as exc:st.warning(str(exc))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning('crm_page_unavailable route=%s type=%s',route,type(exc).__name__)
        st.warning('This CRM section is temporarily unavailable. Refresh to try again.')


def render_page(route,user,navigate=lambda _:None,**dependencies):
    st.html('<style>[data-testid="stMainBlockContainer"]:has(.st-key-crm-workspace){padding-top:4rem} .st-key-crm-workspace [data-testid="stForm"]{padding:.65rem} .st-key-crm-workspace h3{font-size:1.3rem}</style>')
    with st.container(key='crm-workspace'):
        if route not in ('CRM Campaigns','CRM Automations'):
            _render_page(route,user,navigate,**dependencies)
            return
        from email_loading import stage
        require(user,PAGE_KEYS[route])
        with stage(route, 'render'):
            _render_page(route,user,navigate,**dependencies)
