"""Premium Automations overview; detail queries run only on explicit opening."""
from html import escape
from urllib.parse import urlencode
from time import monotonic
from base64 import b64encode
import streamlit as st
from crm_automation_definition import TRIGGERS, native
from crm_automation_home_data import counts, rows, PAGE_SIZE, reporting_window, step_metrics
from crm_automation_analytics import summary, activity, performance, revenue, conversions, checkout_page, flow_state, add_to_flow
from crm_campaign_home import STYLE, ICON_PATHS, arm_home_poll
from crm_campaign_home_cache import resolve
from crm_logic import now, date

STYLE_AUTO='''<style>
.sc-auto-kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:4px 0 8px}
.sc-auto-kpi{display:flex;gap:10px;padding:16px 12px;border:1px solid #e8e6e1;border-radius:12px;background:#fff;min-width:0;align-items:flex-start;min-height:116px}
.sc-auto-kpi small{color:#73747c;font-size:11px;display:block}.sc-auto-kpi strong{display:block;font-size:24px;margin:6px 0;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.sc-auto-trend{font-size:11px;color:#328555;min-height:16px}
.sc-auto-kpi .sc-home-icon{width:38px;height:38px}
.st-key-crm-campaign-home button[kind='primary']{background:#d1a638!important;border-color:#d1a638!important;color:#161820!important;font-weight:600}
.st-key-crm-campaign-home h1+p{margin-top:2px;margin-bottom:10px}
.st-key-auto-create button{max-width:280px;float:right}
.sc-auto-trend{color:#71747c}.sc-auto-kpi strong{line-height:1.25}.sc-auto-kpi{min-height:110px}
.sc-auto-head,.sc-auto-row{font-size:13px}.sc-auto-head{font-size:12px}.sc-auto-row small{font-size:12px}
.sc-auto-head,.sc-auto-row{display:grid;grid-template-columns:minmax(180px,2.6fr) minmax(105px,1.3fr) repeat(7,minmax(45px,.65fr)) 70px;gap:12px;align-items:center;font-size:12px;padding:10px 0;min-width:0;border-bottom:1px solid #eee}
.sc-auto-head{background:#f8f8f8;border-radius:7px;padding:9px 4px;margin-right:48px;position:relative;color:#646770;font-size:11px}.sc-auto-head::after{content:'Actions';position:absolute;right:-48px;width:44px}
.sc-auto-row>div{min-width:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.sc-auto-row>div:nth-child(n+3){text-align:right}.sc-auto-row small{display:block;color:#7a7c85;font-size:11px;margin-top:4px}.sc-auto-name{display:flex;gap:10px;align-items:center}.sc-auto-name a{color:#22242a;text-decoration:none;font-weight:600}.sc-auto-name .sc-home-icon{width:36px;height:36px}
.sc-auto-pill{display:inline-block;border-radius:7px;background:#f0f1f4;padding:6px 9px;font-size:11px}.sc-auto-pill.active{background:#e7f7ef;color:#21613d}
[class*='st-key-auto-row-']{gap:8px!important}[class*='st-key-auto-actions-'] button{min-height:36px!important;width:36px!important;padding:5px!important;border:1px solid #e4e3df!important;border-radius:7px!important;background:#fff!important;color:#52565e!important}
[class*='st-key-auto-actions-'] button:hover,[class*='st-key-auto-actions-'] button[aria-expanded='true']{background:#f2f1ed!important;border-color:#cfcec7!important}
[class*='st-key-auto-actions-'] button:focus-visible{outline:2px solid #b68e2c!important;outline-offset:2px}
[data-testid='stPopoverBody']:has([class*='st-key-auto-context-menu-']){width:190px!important;min-width:0!important;max-width:calc(100vw - 24px)!important;padding:5px!important;border:1px solid #deddd7!important;border-radius:9px!important;background:#fffefa!important;box-shadow:0 5px 18px #171a2024!important}
[class*='st-key-auto-context-menu-']{gap:2px!important}
[class*='st-key-auto-context-menu-'] [data-testid='stElementContainer']{margin:0!important}
[class*='st-key-auto-context-menu-'] button{width:100%!important;min-height:34px!important;justify-content:flex-start!important;padding:6px 10px!important;border:0!important;border-radius:5px!important;background:transparent!important;color:#30343b!important;box-shadow:none!important;font-size:13px!important}
[class*='st-key-auto-context-menu-'] button p{font-size:13px!important}
[class*='st-key-auto-context-menu-'] button>div,[class*='st-key-auto-context-menu-'] [data-has-shortcut]{width:100%!important;justify-content:flex-start!important}
[class*='st-key-auto-context-menu-'] [data-testid='stIconMaterial']{font-size:18px!important;width:18px;flex:none}
[class*='st-key-auto-context-menu-'] button:hover:not(:disabled){background:#efeee9!important}
[class*='st-key-auto-context-menu-'] button:focus-visible{outline:2px solid #b68e2c!important;outline-offset:-2px;background:#efeee9!important}
[class*='st-key-auto-context-menu-'] button:disabled{opacity:.4!important}
[class*='st-key-auto-context-menu-'] [class*='st-key-auto_delete_']{border-top:1px solid #e9e7e1;padding-top:3px;margin-top:3px}
[class*='st-key-auto-context-menu-'] [class*='st-key-auto_delete_'] button:not(:disabled){color:#a43838!important}
[class*='st-key-auto-context-menu-'] [class*='st-key-auto_delete_'] button:hover:not(:disabled){background:#f9ecea!important}
.st-key-auto-overview{border:1px solid #e8e6e1;border-radius:12px;padding:14px;background:#fff;container-type:inline-size}
.sc-auto-activity{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.sc-auto-event{padding:14px;border:1px solid #e8e6e1;border-radius:10px;background:#fff;min-width:0;font-size:12px}.sc-auto-event small{display:block;color:#797c86;margin:6px 0}.sc-auto-event strong{overflow-wrap:anywhere}
.st-key-auto-home-tabs button[aria-pressed='true']{border-bottom:2px solid #c7a13f!important;font-weight:600!important}
.st-key-auto-home-tabs button{border-radius:0!important;border:0!important;background:transparent!important;min-height:38px}
.st-key-auto-home-tabs button[kind='segmented_controlActive']{border-bottom:2px solid #c7a13f!important;color:#161820!important;font-weight:600!important}
[class*='st-key-auto-actions-'] [data-testid='stPopoverButton'] svg{display:none}
[class*='st-key-auto-actions-'] [data-testid='stPopoverButton'] [data-testid='stIconMaterial']{display:none}
.sc-auto-head,.sc-auto-row{font-size:13px}.sc-auto-head{font-size:12px}.sc-auto-row small{font-size:12px}
.sc-auto-person{display:flex;align-items:center;gap:10px}.sc-auto-avatar{display:grid;place-items:center;width:36px;height:36px;flex:none;border-radius:50%;background:#edf3fb;color:#315898;font-weight:600}
.st-key-auto-activity{border:1px solid #e8e6e1;border-radius:12px;background:#fff;padding:14px;margin-top:6px}.st-key-auto-activity h3{font-size:20px;padding-top:0;padding-bottom:0}
.st-key-auto-overview input{background:#fff;border:1px solid #e6e9ef;border-radius:7px}
@media(max-width:1400px){.sc-auto-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@container(max-width:1080px){.sc-auto-head,.sc-auto-row{grid-template-columns:minmax(170px,2fr) minmax(95px,1fr) repeat(4,minmax(45px,.7fr)) 70px}.sc-auto-head>div:nth-child(5),.sc-auto-row>div:nth-child(5),.sc-auto-head>div:nth-child(6),.sc-auto-row>div:nth-child(6),.sc-auto-head>div:nth-child(9),.sc-auto-row>div:nth-child(9){display:none}}
@container(max-width:710px){.sc-auto-head,.sc-auto-row{grid-template-columns:minmax(100px,2fr) 48px 60px;gap:8px}.sc-auto-head>div:nth-child(2),.sc-auto-row>div:nth-child(2),.sc-auto-head>div:nth-child(3),.sc-auto-row>div:nth-child(3),.sc-auto-head>div:nth-child(7),.sc-auto-row>div:nth-child(7),.sc-auto-head>div:nth-child(8),.sc-auto-row>div:nth-child(8){display:none}}
@media(max-width:750px){.sc-auto-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.sc-auto-kpi{padding:12px 8px;gap:7px}.sc-auto-kpi strong{font-size:21px}.sc-auto-activity{grid-template-columns:repeat(2,minmax(0,1fr))}.st-key-auto-overview{padding:8px}}
@media(max-width:390px){.sc-auto-kpi .sc-home-icon{width:26px;height:28px}.sc-auto-kpi small{font-size:10px}.sc-auto-name .sc-home-icon{display:none}.sc-auto-activity{grid-template-columns:1fr}}
</style>'''

# Native popover owns placement and outside-click dismissal. Delegated keyboard
# handling adds navigation and reliable Escape dismissal without polling/rerenders.
MENU_SCRIPT='''<script>(()=>{
if(window.scAutomationMenuKeys)return;
window.scAutomationMenuKeys=true;
const decorate=root=>{
 const menus=[...(root.querySelectorAll?.("[class*='st-key-auto-context-menu-']")||[])];
 if(root.matches?.("[class*='st-key-auto-context-menu-']"))menus.push(root);
 for(const menu of menus){
  menu.setAttribute('role','group');menu.setAttribute('aria-label','Automation actions');
  menu.querySelectorAll('[data-testid="stIconMaterial"]').forEach(icon=>icon.setAttribute('aria-hidden','true'));
 }
};
decorate(document);
new MutationObserver(records=>records.forEach(r=>r.addedNodes.forEach(decorate)))
 .observe(document.body,{childList:true,subtree:true});
const close=menu=>{
 if(!menu?.isConnected)return;
 const key=[...menu.classList].find(c=>c.startsWith('st-key-auto-context-menu-'));
 const id=key?.slice('st-key-auto-context-menu-'.length);
 const trigger=[...document.querySelectorAll('[class*="st-key-auto_actions_'+id+'"] button')]
  .find(b=>b.getClientRects().length);
 if(trigger){trigger.click();trigger.focus();}
};
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'){
  const opened=document.querySelector("[data-testid='stPopoverBody'] [class*='st-key-auto-context-menu-']");
  if(opened){e.preventDefault();e.stopPropagation();close(opened);}
  return;
 }
 const menu=e.target.closest?.("[class*='st-key-auto-context-menu-']");
 if(!menu||!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;
 const items=[...menu.querySelectorAll('button:not(:disabled)')];
 if(!items.length)return;
 e.preventDefault();
 const index=items.indexOf(document.activeElement);
 const next=e.key==='Home'?0:e.key==='End'?items.length-1:
 (index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;
 items[next].focus();
},true);
document.addEventListener('click',e=>{
 const item=e.target.closest?.("[class*='st-key-auto-context-menu-'] button:not(:disabled)");
 if(!item)return;
 const menu=item.closest("[class*='st-key-auto-context-menu-']");
 // Let the native action receive the click before dismissing its popover.
 setTimeout(()=>close(menu),0);
});
})();</script>'''


def money(values):
    if values is None:return '—'
    return ' · '.join(str(k)+' '+format(float(v),',.2f') for k,v in sorted(values.items())) or '—'


def percentage(n,d):return '—' if not d else format(100*float(n or 0)/float(d),'.1f')+'%'


def icon(index,colour='green'):
    paths=ICON_PATHS[index] if index<len(ICON_PATHS) else '<path d="M4 20v-5m8 5V9m8 11V3"/>'
    if index==6:paths='<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>'
    if index==7:paths='<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/>'
    if index==8:paths='<path d="m3 7 9-5 9 5v10l-9 5-9-5V7Zm0 0 9 5 9-5M12 12v10M7 4l10 6"/>'
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'+{'green':'#218148','blue':'#2665d8','purple':'#8058ad','gold':'#947021','rose':'#af5268'}[colour]+'" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+paths+'</svg>'
    return '<span class="sc-home-icon '+colour+'" aria-hidden="true"><img alt="" src="data:image/svg+xml;base64,'+b64encode(svg.encode()).decode()+'"></span>'


def kpi_html(data):
    prior=data.get('previous',{})
    cards=[]
    specs=[('Active automations','active',0,'green'),('Emails sent (30 days)','sent_emails',1,'blue'),
           ('Delivery rate','delivery_rate',0,'green'),('Open rate','open_rate',6,'blue'),
           ('Click rate','click_rate',3,'purple'),('Revenue from automations (30 days)','revenue',5,'gold')]
    for label,key,glyph,colour in specs:
        value=data.get(key);old=prior.get(key);trend='Current published flows' if key=='active' else 'No prior-period comparison'
        if key=='revenue':
            text=money(value)
            if value and old and len(value)==len(old)==1 and set(value)==set(old):
                v=float(next(iter(value.values())));o=float(next(iter(old.values())))
                if o:trend=f'{(v-o)/o*100:+.1f}% vs. last 30 days'
        else:
            text='—' if value is None else format(float(value),'.1f')+'%' if key.endswith('_rate') else format(int(value),',')
            if value is not None and old is not None:
                if key.endswith('_rate'):trend=f'{float(value)-float(old):+.1f} pp vs. last 30 days'
                elif old:trend=f'{(float(value)-float(old))/float(old)*100:+.1f}% vs. last 30 days'
        if key not in data:text='<span class="sc-home-unresolved" aria-label="Loading"></span>'
        else:text=escape(text)
        cards.append('<div class="sc-auto-kpi">'+icon(glyph,colour)+'<div><small>'+escape(label)+'</small><strong>'+text+'</strong><div class="sc-auto-trend">'+escape(trend)+'</div></div></div>')
    return '<div class="sc-auto-kpis">'+''.join(cards)+'</div>'


def payload(key,load):
    value=load()
    fields={'counts':('active','all_count','drafts','paused','archived'),
            'delivery':('sent_emails','delivery_rate','open_rate','click_rate','revenue','previous')}.get(key[0])
    if fields and (not isinstance(value,dict) or not all(k in value for k in fields)):
        raise ValueError('Incomplete automation summary')
    if key[0]=='counts' and any(value[k] is None for k in fields):raise ValueError('Incomplete automation counts')
    if key[0]=='delivery' and (value['sent_emails'] is None or not isinstance(value['revenue'],dict) or not isinstance(value['previous'],dict)):
        raise ValueError('Incomplete automation metrics')
    if key[0]=='profiles':
        if not isinstance(value,dict):raise ValueError('Incomplete customer labels')
    elif not fields and not isinstance(value,list):raise ValueError('Incomplete automation list')
    return [value]


def read(store,key,load):
    from crm_automation_ui import home_state,job
    state=home_state()
    # Reuse stable session cache without changing Campaigns' validation contract.
    value,status=resolve(state,store,key,job(state,store,key,lambda:payload(key,load)))
    state.setdefault('activity',{})[key[0]]=status
    if status=='ERROR':st.caption('Could not refresh this section. Last verified data remains visible.')
    return value[0] if value else None


def activity_html(events,profiles=None):
    profiles=profiles or {}
    cards=[]
    for event in events:
        stamp=date(event['occurred_at']);elapsed=max(0,int((now()-stamp).total_seconds())) if stamp else None
        age='Just now' if elapsed is not None and elapsed<60 else str(elapsed//60)+' min ago' if elapsed is not None and elapsed<3600 else stamp.strftime('%d %b · %H:%M UTC') if stamp else '—'
        customer=profiles.get(event.get('customer_id')) or 'Customer '+str(event.get('customer_id') or 'unavailable').rsplit('/',1)[-1]
        initials=''.join(p[0] for p in customer.split()[:2])
        cards.append('<div class="sc-auto-event"><div class="sc-auto-person"><span class="sc-auto-avatar">'+escape(initials)+'</span><strong>'+escape(customer)+'</strong></div><small>'+escape(event['name'])+'</small><span>'+escape(event['event'])+'</span><small>'+escape(age)+'</small></div>')
    return '<div class="sc-auto-activity">'+''.join(cards)+'</div>'


@st.dialog('Automation analytics',width='large')
def analytics(shop,store,user,identity):
    row=store.get('automations',identity)
    if not row or row['config'].get('deleted_at'):st.warning('Automation unavailable.');return
    st.subheader(row['name']);window=reporting_window()
    st.caption('Performance · rolling 30 days UTC. Provider submission is separate from delivery.')
    history=performance(store,identity,window)
    total={k:sum(r[k] for r in history) for k in ('sent','delivered','opened','clicked')}
    total['conversions']=conversions(store,identity,window)
    columns=st.columns(5)
    for col,key in zip(columns,total):col.metric(key.title(),format(total[key],','))
    if history:st.line_chart(history,x='day',y=['sent','delivered','opened','clicked'],height=210)
    else:st.caption('No accepted sends in this reporting period.')
    st.caption('Revenue · '+money(revenue(store,window,identity)['revenue']))
    if row['trigger_type']=='abandoned':checkout_analytics(shop,store,user,row)
    else:
        metrics=step_metrics(store,identity)
        st.dataframe(metrics,hide_index=True,use_container_width=True)
    events=activity(store,identity,12)
    st.subheader('Recent activity')
    if events:st.html(activity_html(events))
    else:st.caption('No recorded activity yet.')


@st.fragment(run_every='1s')
def countdown(checkout):
    label,next_action=flow_state(checkout)
    st.caption(label+' · '+next_action)


@st.fragment(run_every='20s')
def checkout_analytics(shop,store,user,row):
    st.subheader('Abandoned checkouts')
    st.caption('Shopify checkout list with this flow’s signed checkout, journey and email state.')
    slot='auto_checkout_page_'+str(row['id'])
    cursor=st.session_state.get(slot+'_cursor')
    try:
        page=checkout_page(shop,store,row['id'],cursor)
        st.session_state[slot]=page
    except Exception:
        page=st.session_state.get(slot)
        st.caption('Shopify checkout refresh unavailable. Last loaded page is retained.')
        if not page:return
    listing=[]
    for c in page['nodes']:
        customer=c.get('customer') or {};ledger=c.get('ledger') or {};state,next_action=flow_state(c)
        sent={s['step']:s['status'] for s in ledger.get('sends',[])}
        price=(c.get('totalPriceSet') or {}).get('shopMoney') or {}
        listing.append({'Checkout':c['id'].rsplit('/',1)[-1],'Customer':' '.join(filter(None,[customer.get('firstName'),customer.get('lastName')])) or 'Guest',
          'Email':customer.get('email') or '—','Region':(c.get('shippingAddress') or c.get('billingAddress') or {}).get('countryCodeV2') or '—',
          'Total':money({price['currencyCode']:price['amount']}) if price else '—','Recovery':'Recovered' if state=='Recovered' else 'Not recovered',
          'Flow status':state,'Email 1':'Sent' if sent.get(0)=='ACCEPTED' else sent.get(0,'Not sent'),
          'Email 2':'Sent' if sent.get(1)=='ACCEPTED' else sent.get(1,'Not sent'),
          'Opened':ledger.get('opened') or 0,'Clicked':ledger.get('clicked') or 0,'Last activity':str(ledger.get('last_activity_at') or c.get('updatedAt') or ''),
          'Next action':next_action})
    selection=st.dataframe(listing,hide_index=True,use_container_width=True,on_select='rerun',selection_mode='single-row',key=slot+'_table')
    selected=selection.selection.rows
    if selected and 0<=selected[0]<len(page['nodes']):
        checkout=page['nodes'][selected[0]];countdown(checkout)
        ledger=checkout.get('ledger') or {};state,_=flow_state(checkout)
        eligible=bool(ledger) and not ledger.get('enrollment_id') and state!='Recovered' and ledger.get('automation_status')=='ACTIVE' and row['status']=='ACTIVE' and native(row)
        if eligible:
            st.caption('Adds to the published flow after fresh eligibility checks. Existing inactivity and email delays apply.')
            confirmed=st.checkbox('Confirm adding this checkout to the published flow',key=slot+'_confirm_'+checkout['id'])
            if st.button('Add to flow',disabled=not confirmed,type='primary',key=slot+'_add_'+checkout['id']):
                try:
                    add_to_flow(shop,store,user,str(row['id']),checkout['id'])
                    from crm_automation_ui import changed,home_state
                    changed()
                    cache=home_state().get('campaign_home_cache',{})
                    for key in list(cache):
                        if key[1][0]=='activity':cache.pop(key)
                    st.session_state.pop(slot,None);st.toast('Added to flow · delivery remains with the background worker.');st.rerun(scope='fragment')
                except (ValueError,PermissionError) as exc:st.warning(str(exc))
        elif not ledger.get('enrollment_id') and state!='Recovered':st.caption('Add to flow requires an active published flow and a signed, eligible checkout receipt.')
    if page['pageInfo'].get('hasNextPage') and st.button('Next checkout page',key=slot+'_next'):
        st.session_state[slot+'_cursor']=page['pageInfo']['endCursor'];st.rerun(scope='fragment')
    if cursor and st.button('Newest checkouts',key=slot+'_first'):
        st.session_state.pop(slot+'_cursor',None);st.rerun(scope='fragment')


@st.dialog('Archive automation?',width='small')
def archive_dialog(store,user,row):
    from crm_automation_ui import changed
    st.write(row['name']);st.caption('Archive pauses this flow and preserves all journey and email history.')
    if st.button('Cancel',key='auto_archive_cancel'):st.rerun()
    if st.button('Archive',type='primary',key='auto_archive_confirm'):
        if row['category']=='Active':store.lifecycle(user,row['id'],'pause')
        store.lifecycle(user,row['id'],'archive');changed();st.rerun()


def table(shop,store,user):
    from crm_automation_ui import open_flow,changed,delete_dialog
    with st.container(key='auto-overview'):
        search,trigger,sort=st.columns([4,1.1,1.1])
        query=search.text_input('Search automations',placeholder='Search automations...',label_visibility='collapsed',key='auto_search')
        kind=trigger.selectbox('Trigger',['All',*TRIGGERS],format_func=lambda k:'All triggers' if k=='All' else TRIGGERS[k][1],label_visibility='collapsed',key='auto_filter')
        order=sort.selectbox('Sort',['Newest first','Oldest first'],label_visibility='collapsed',key='auto_sort')
        from crm_automation_ui import home_state
        state=home_state();criteria=(query,kind,order)
        if state.get('criteria')!=criteria:state['offset']=0;state['criteria']=criteria
        offset=state.get('offset',0)
        records=read(store,('table',criteria,offset),lambda:rows(store,search=query,trigger=kind,oldest=order=='Oldest first',offset=offset))
        if records is None:st.caption('Loading automations…');return
        labels=('Automation','Trigger','Entered','Sent','Delivery %','Open %','Click %','Conversions','Revenue','Status')
        # Actions occupy a native Streamlit popover next to the grid.
        st.html('<div class="sc-auto-head">'+''.join('<div>'+s+'</div>' for s in labels)+'</div>')
        for row in records[:PAGE_SIZE]:
            with st.container(horizontal=True,key='auto-row-'+str(row['id'])):
                with st.container(width='stretch'):
                    label=TRIGGERS.get(row['trigger_type'],('','Legacy flow'))[1]
                    category=row['category'].rstrip('s')
                    target='?'+urlencode({'page':'CRM Automations','automation':str(row['id'])})
                    glyph,colour={'welcome':(7,'blue'),'post_purchase':(8,'gold'),'fulfilled':(8,'green'),'winback':(4,'rose')}.get(row['trigger_type'],(0,'gold'))
                    name='<div class="sc-auto-name">'+icon(glyph,colour)+'<div><a href="'+escape(target,quote=True)+'" target="_self">'+escape(row['name'])+'</a><small>'+escape(label)+'</small></div></div>'
                    values=[name,escape(label),format(row['entered'],','),format(row['sent'],','),percentage(row['delivered'],row['sent']),
                      percentage(row['opened'],row['delivered']),percentage(row['clicked'],row['delivered']),format(row['orders'],','),escape(money(row.get('revenue'))),
                      '<span class="sc-auto-pill '+('active' if category=='Active' else '')+'">'+escape(category)+'</span>']
                    st.html('<div class="sc-auto-row">'+''.join('<div>'+s+'</div>' for s in values)+'</div>')
                with st.container(width=40,key='auto-actions-'+str(row['id'])):
                    with st.popover('⋮',help='Automation actions',key='auto_actions_'+str(row['id'])):
                        with st.container(key='auto-context-menu-'+str(row['id']),gap='small'):
                            if st.button('Analytics',icon=':material/bar_chart:',use_container_width=True,key='auto_analytics_'+str(row['id'])):analytics(shop,store,user,row['id'])
                            if st.button('Open editor',icon=':material/edit:',use_container_width=True,key='auto_open_'+str(row['id'])):open_flow(row['id'])
                            if st.button('Duplicate',icon=':material/content_copy:',use_container_width=True,key='auto_duplicate_'+str(row['id'])):
                                duplicate=store.duplicate(user,row['id']);changed();open_flow(duplicate['id'])
                            if st.button('Archive',icon=':material/archive:',use_container_width=True,disabled=category=='Archived',key='auto_archive_'+str(row['id'])):archive_dialog(store,user,row)
                            if st.button('Delete',icon=':material/delete:',use_container_width=True,disabled=category not in ('Draft','Archived'),help='Archive first to retain active flow safety.' if category not in ('Draft','Archived') else None,key='auto_delete_'+str(row['id'])):delete_dialog(store,user,row)
        if not records:st.caption('No automations match this view.')
        st.caption('Showing '+str(offset+1 if records else 0)+'–'+str(offset+min(len(records),PAGE_SIZE))+' · click an automation to edit its settings.')
        prev,nxt=st.columns(2)
        if prev.button('Previous',disabled=offset==0,key='auto_previous'):state['offset']=max(0,offset-PAGE_SIZE);st.rerun()
        if nxt.button('Next',disabled=len(records)<=PAGE_SIZE,key='auto_next'):state['offset']=offset+PAGE_SIZE;st.rerun()


def home(shop,store,user):
    from crm_automation_ui import home_state,chooser
    state=home_state();st.html(STYLE+STYLE_AUTO)
    st.html(MENU_SCRIPT,unsafe_allow_javascript=True)
    with st.container(key='crm-campaign-home'):
        title,create=st.columns([4,1],vertical_alignment='center')
        title.html('<h1>Automations</h1><p style="color:#73747c">Track performance across every email flow.</p>')
        with create.container(key='auto-create'):
            if st.button('+ Create automation',type='primary',use_container_width=True):chooser(store,user)
        stamp=monotonic()
        if 'window' not in state or stamp-state.get('window_stamp',0)>=20:state['window']=reporting_window();state['window_stamp']=stamp
        # Independent jobs start in one render; no Shopify calls on Home.
        from crm_automation_ui import job
        for key,load in ((('counts',None),lambda:counts(store)),(('delivery',None),lambda:summary(store,state['window'])),(('activity',None),lambda:activity(store))):
            job(state,store,key,lambda key=key,load=load:payload(key,load))
        count=read(store,('counts',None),lambda:counts(store)) or {}
        stats=read(store,('delivery',None),lambda:summary(store,state['window'])) or {}
        st.html(kpi_html({**stats,**count}))
        tab=st.segmented_control('Automation view',['Overview','Recent Activity'],default='Overview',label_visibility='collapsed',key='auto-home-tabs') or 'Overview'
        events=read(store,('activity',None),lambda:activity(store))
        profiles={}
        if events and shop is not None:
            identities=tuple(sorted({e['customer_id'] for e in events if e.get('customer_id')}))
            def labels():
                return {c['id']:(' '.join(filter(None,[c.get('firstName'),c.get('lastName')])) or 'Customer '+c['id'].rsplit('/',1)[-1]) for c in shop.customer_batch(list(identities))}
            profiles=read(store,('profiles',identities),labels) or {}
        if tab=='Overview':table(shop,store,user)
        with st.container(key='auto-activity'):
            st.subheader('Recent activity');st.caption('Recorded automation events · updates every 20 seconds while this page is open.')
            if events:st.html(activity_html(events[:4] if tab=='Overview' else events,profiles))
            elif events is not None:st.caption('No recorded automation activity yet.')
            else:st.caption('Loading recent activity…')
        with st.container(key='crm-auto-home-poll'):st.button('Refresh automation data',key='crm-auto-home-poll-tick')
        st.html('<style>.st-key-crm-auto-home-poll{display:none}</style>')
    pending=any(s in ('UNRESOLVED','LOADING','REFRESHING') for s in state.get('activity',{}).values())
    arm_home_poll(key='crm-auto-home-poll',seconds=.25 if pending else 20)
