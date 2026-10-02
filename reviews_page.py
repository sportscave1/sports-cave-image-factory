"""Reviews: one route, three lightweight areas; shared OS read pool and styling."""
from copy import deepcopy
from datetime import timedelta
from html import escape
import hashlib
import streamlit as st
from reviews_store import ReviewsStore,require
from reviews_cache import read,invalidate
from reviews_model import FIELDS,auto_mapping,product_gid
from crm_logic import now
from crm_campaign_home import STYLE

STYLE_REVIEW='''<style>
[data-testid="stMainBlockContainer"]:has(.st-key-sc-reviews){max-width:none;padding:calc(var(--sc-topbar-height,64px) + 20px) 24px 20px!important}
.st-key-sc-reviews{margin-top:-32px;color:#171820}.st-key-sc-reviews h1{font-size:30px;margin:0}
.st-key-sc-reviews [data-testid="stVerticalBlock"]{gap:8px}.st-key-sc-reviews button:focus-visible{outline:2px solid #b99232;outline-offset:2px}
.st-key-reviews-tabs button,.st-key-reviews-status button{border:0!important;border-radius:0!important;background:transparent!important;border-bottom:2px solid transparent!important}
.st-key-reviews-tabs button[kind="segmented_controlActive"],.st-key-reviews-status button[kind="segmented_controlActive"]{border-bottom-color:#b99232!important;color:#171820!important}
.rv-row,.rv-head{display:grid;grid-template-columns:1.1fr 1.2fr .5fr 2.3fr .7fr .6fr .65fr;gap:12px;align-items:center;min-width:0}
.rv-row{font-size:13px;padding:12px 0;border-bottom:1px solid #eae6df}.rv-row>div{min-width:0;overflow-wrap:anywhere}.rv-head{font-size:10px;color:#777;padding:10px 0;border-bottom:1px solid #eae6df}
.rv-row small{display:block;color:#73737a;font-size:11px;margin-top:4px}.rv-stars{color:#947021;letter-spacing:1px;white-space:nowrap}
.rv-product{display:flex;gap:8px;align-items:center}.rv-product img{width:42px;height:42px;object-fit:contain;flex:none;border-radius:4px}
.rv-pill{display:inline-block;background:#eff0ee;padding:4px 7px;border-radius:5px;font-size:11px}.rv-pill.published{color:#28763a;background:#edf6ee}.rv-pill.pending{background:#faf3df;color:#806421}
.st-key-reviews-table{padding:12px;border:1px solid #e9e6e0;border-radius:12px;background:white;min-width:0}
.st-key-reviews-poll{display:none}.st-key-sc-reviews [data-testid="stHorizontalBlock"]{min-width:0}
@media(max-width:1000px){.rv-row,.rv-head{grid-template-columns:1fr 1fr .5fr 2fr .65fr}.rv-date,.rv-source{display:none}}
.st-key-reviews-tabs [data-testid="stWidgetLabel"],.st-key-reviews-status [data-testid="stWidgetLabel"]{display:none}
@media(max-width:640px){[data-testid="stMainBlockContainer"]:has(.st-key-sc-reviews){padding-left:12px!important;padding-right:12px!important}.rv-head{display:none}.rv-row{grid-template-columns:1fr 1fr}.rv-copy{grid-column:1/-1}.rv-product img{width:32px;height:32px}.rv-stars{font-size:12px}.st-key-sc-reviews [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-sc-reviews [data-testid="stColumn"]{min-width:0!important}.st-key-reviews-filters [data-testid="stColumn"]{flex:1 1 120px!important;min-width:120px!important}.st-key-reviews-filters [data-testid="stColumn"]:first-child{flex-basis:100%!important}}
</style>'''

def state():return st.session_state.setdefault('reviews_state',{})
def load(key,fn,ttl=60):
    value,activity=read(state(),key,fn,ttl);state().setdefault('activity',{})[key[0]]=activity
    return value,activity
def changed(*groups):invalidate(state(),*groups)

def kpi_html(data=None):
    data=data or {};values=(('Average rating',None if data.get('average') is None else f"{data['average']:.1f}",':material/star:'),
      ('Total reviews',data.get('total'),''),('Reviews (30 days)',data.get('recent'),''),
      ('5-star rate',None if data.get('five_rate') is None else f"{data['five_rate']:.1f}%",''),('Needs attention',data.get('attention'),''))
    from base64 import b64encode
    # Same compact inline icon technique as Campaign Home; no external font load.
    paths=('<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z"/>',
      '<path d="M4 4h16v12H8l-4 4Z"/><path d="M8 8h8M8 12h5"/>',
      '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>',
      '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z"/>',
      '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16v1"/>')
    colours=('green','blue','gold','purple','rose');palette=('#218148','#2380b5','#947021','#8058ad','#af5268');cards=[]
    for i,(label,value,_) in enumerate(values):
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="'+palette[i]+'" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+paths[i]+'</svg>'
        icon='<img src="data:image/svg+xml;base64,'+b64encode(svg.encode()).decode()+'" width="21" height="21" alt="">'
        cards.append('<div class="sc-home-kpi"><div class="sc-home-icon '+colours[i]+'">'+icon+'</div><div><small>'+label+'</small><strong>'+('—' if value is None else escape(f'{value:,}' if isinstance(value,int) else str(value)))+'</strong></div></div>')
    return '<div class="sc-home-kpis">'+''.join(cards)+'</div>'

def row_html(r):
    from crm_campaign_html import email_image_url
    image=email_image_url(r.get('product_image',''));at=str(r['created_at'])[:10] if (r.get('source_metadata') or {}).get('date_known',True) else 'Unknown'
    product=('<img src="'+escape(image,quote=True)+'" alt="" loading="lazy" width="42" height="42">' if image else '')+escape(r.get('product_title') or 'Needs product match')
    return '<div class="rv-row"><div>'+escape(r['reviewer_name'])+('<small>Verified purchase</small>' if r['verified_purchase'] else '')+'</div><div class="rv-product">'+product+'</div><div class="rv-stars" aria-label="'+str(r['rating'])+' out of 5">'+'★'*r['rating']+'☆'*(5-r['rating'])+'</div><div class="rv-copy"><b>'+escape(r['title'])+'</b><small>'+escape(r['body'][:160])+('…' if len(r['body'])>160 else '')+'</small></div><div class="rv-date">'+escape(at)+'</div><div class="rv-source">'+escape({'judgeme':'Judge.me','csv':'CSV','sports_cave':'Sports Cave'}[r['source']])+'</div><div><span class="rv-pill '+r['status'].lower()+'">'+escape(r['status'].title())+'</span></div></div>'

@st.dialog('Review',width='large')
def detail(store,user,identity):
    r=store.get_review(identity)
    if not r:st.warning('Review is unavailable.');return
    stamp=str(r['created_at'])[:10] if (r.get('source_metadata') or {}).get('date_known',True) else 'Date unavailable'
    st.subheader(r.get('product_title') or 'Needs product match');st.caption(r['reviewer_name']+' · '+str(r['rating'])+'/5 · '+stamp+' · '+r['source'])
    if r['verified_purchase']:st.caption('Verified purchase · matched Shopify order, customer and product')
    elif r['source_verified']:st.caption('Source reports verification · not verified by Sports Cave')
    if r['title']:st.write(r['title'])
    st.write(r['body'])
    if r.get('order_id'):
        import os
        shop=os.getenv('SHOPIFY_STORE_DOMAIN','')
        if shop.endswith('.myshopify.com'):st.link_button('Open order','https://'+shop+'/admin/orders/'+r['order_id'].rsplit('/',1)[-1])
    if r.get('customer_id'):
        import os
        shop=os.getenv('SHOPIFY_STORE_DOMAIN','')
        if shop.endswith('.myshopify.com'):st.link_button('Open customer','https://'+shop+'/admin/customers/'+r['customer_id'].rsplit('/',1)[-1])
    reply=st.text_area('Merchant reply',value=r['merchant_reply'],max_chars=3000,height=100)
    st.caption('Saved to Sports Cave and its storefront. External provider replies are not updated.')
    left,right=st.columns(2)
    if left.button('Save reply',type='primary'):
        store.moderate(user,identity,reply=reply);changed('table','summary');st.rerun()
    target='PENDING' if r['status']=='PUBLISHED' else 'PUBLISHED'
    if right.button('Unpublish' if target=='PENDING' else 'Publish'):
        store.moderate(user,identity,status=target);changed('table','summary');st.rerun()
    archive,spam=st.columns(2)
    if archive.button('Archive',icon=':material/archive:'):
        store.moderate(user,identity,status='ARCHIVED');changed('table','summary');st.rerun()
    if spam.button('Mark spam',icon=':material/block:'):
        store.moderate(user,identity,status='SPAM');changed('table','summary');st.rerun()
    with st.expander('Resolve product' if not r['product_id'] else 'Change product match'):
        query=st.text_input('Find product',key='review_match_search')
        choices=store.products(query)
        if choices:
            picked=st.selectbox('Product',choices,format_func=lambda p:p['title'],key='review_match_product')
            if st.button('Save product match'):
                store.moderate(user,identity,product=picked['shopify_product_id']);changed('table','summary');st.rerun()

@st.fragment
def overview(store,user):
    with st.container(key='reviews-summary'):
        value,activity=load(('summary',),store.summary)
        st.html(kpi_html(value))
        if activity=='ERROR':st.caption('Statistics could not refresh. Last resolved values remain visible.')
    with st.container(key='reviews-table'):
        labels={'All reviews':'all','Pending':'PENDING','Needs reply':'reply','Archived':'ARCHIVED'}
        status=st.segmented_control('Review status',list(labels),default='All reviews',key='reviews-status') or 'All reviews'
        with st.container(key='reviews-filters'):
            a,b,c,d,e=st.columns([2,1.5,1,1,1])
            search=a.text_input('Search reviews',label_visibility='collapsed',placeholder='Search reviews…',key='rv_search')
            product=b.text_input('Product',placeholder='Product name / handle',label_visibility='collapsed',key='rv_product')
            rating=c.selectbox('Rating',range(6),format_func=lambda n:str(n)+' stars' if n else 'All ratings',label_visibility='collapsed')
            source=d.selectbox('Source',['','csv','judgeme','sports_cave'],format_func=lambda v:{'':'All sources','csv':'CSV','judgeme':'Judge.me','sports_cave':'Sports Cave'}[v],label_visibility='collapsed')
            period=e.selectbox('Date',[0,30,90],format_func=lambda n:str(n)+' days' if n else 'All dates',label_visibility='collapsed')
        signature=(labels[status],search,product,rating,source,period)
        if state().get('filters')!=signature:state()['filters']=signature;state()['offset']=0
        offset=state().get('offset',0)
        def table():
            matched=store.match_product({'product_handle':product,'product_title':product}) if product else None
            if product and not matched:return []
            return store.rows(status=labels[status],search=search,product=matched['shopify_product_id'] if matched else '',rating=rating,source=source,since=now()-timedelta(days=period) if period else None,offset=offset)
        rows,activity=load(('table',signature,offset),table)
        if activity=='ERROR':st.caption('Reviews could not refresh. Last resolved rows remain visible.')
        head,actions=st.columns([12,1])
        head.html('<div class="rv-head">'+''.join('<div>'+s+'</div>' for s in ('CUSTOMER','PRODUCT','RATING','REVIEW','DATE','SOURCE','STATUS'))+'</div>')
        actions.html('<div class="rv-head">ACTIONS</div>')
        if rows is not None:
            for r in rows[:25]:
                content,action=st.columns([12,1])
                content.html(row_html(r))
                if action.button('Open',key='review_'+str(r['id']),help='Open review and actions',icon=':material/more_horiz:'):detail(store,user,r['id'])
            if not rows:st.caption('No reviews match these filters.')
            previous,next_page=st.columns(2)
            if previous.button('Previous',disabled=offset==0):state()['offset']=max(0,offset-25);st.rerun(scope='fragment')
            if next_page.button('Next',disabled=len(rows)<=25):state()['offset']=offset+25;st.rerun(scope='fragment')
        elif activity=='LOADING':st.caption('Loading reviews…')

@st.fragment
def importer(store,user):
    from reviews_import import read_csv,preview,JudgeMe
    st.subheader('Connected sources');provider=JudgeMe()
    source,_=load(('sources',),lambda:store.q("SELECT value FROM sc_review_settings WHERE key='judgeme'",one=True))
    verified=source and source['value'].get('verified')
    st.write('Judge.me · '+('Last sync verified' if verified else 'Credentials configured · not verified' if provider.configured else 'Not connected'))
    if verified:st.caption('Last sync · '+str(source['value'].get('last_sync','')))
    sync,settings=st.columns([1,3])
    if sync.button('Sync now',disabled=not provider.configured):store.enqueue_sync(user);changed('imports','sources');st.toast('Review sync queued')
    with settings.popover('Settings'):
        st.caption('Use the Judge.me Private API token in server configuration: JUDGEME_PRIVATE_API_TOKEN. The existing SHOPIFY_STORE_DOMAIN identifies the store. No credentials are stored in the browser or review records.')
    st.subheader('Import file');uploaded=st.file_uploader('UTF-8 CSV · up to 10 MB / 10,000 rows',type=['csv'])
    if uploaded:
        data=uploaded.getvalue();digest=hashlib.sha256(data).hexdigest();headers,raw=read_csv(data)
        safe_preview=[{k:v for k,v in row.items() if 'email' not in k.lower()} for row in raw[:5]]
        st.dataframe(safe_preview,hide_index=True,use_container_width=True)
        source=st.selectbox('Import source',['csv','judgeme'],format_func=lambda v:'Judge.me CSV' if v=='judgeme' else 'CSV')
        suggested=auto_mapping(headers);mapping={}
        with st.expander('Column mapping',expanded=True):
            columns=st.columns(3)
            for i,field in enumerate(FIELDS):
                choices=['',*headers];mapping[field]=columns[i%3].selectbox(field.replace('_',' ').title(),choices,index=choices.index(suggested[field]),key='rv_map_'+digest[:10]+field)
        key=('preview',digest,source,tuple(mapping.items()))
        if st.button('Validate import',type='primary'):state()['preview_key']=key
        if state().get('preview_key')==key:
            result,activity=load(key,lambda:preview(raw,mapping,store,source,__import__('os').getenv('SHOPIFY_STORE_DOMAIN','')))
            if result:
                st.caption(f"Ready: {result['ready']:,} · Duplicates: {result['duplicates']:,} · Need product match: {result['unresolved']:,} · Invalid: {len(result['invalid']):,}")
                if result['invalid']:st.dataframe(result['invalid'][:50],hide_index=True)
                if st.button('Confirm import',disabled=not result['items']):
                    store.enqueue_import(user,source,uploaded.name,result['items'],len(result['invalid']));state().pop('preview_key',None);changed('imports');st.toast('Import queued');st.rerun(scope='fragment')
            elif activity=='ERROR':st.caption('Import validation failed. Check file format and storage, then retry.')
            else:st.caption('Validating import…')
    st.subheader('Recent imports')
    jobs,activity=load(('imports',),store.imports,ttl=5)
    if jobs:
        for r in jobs:
            st.caption(r['label']+' · '+r['status'].title()+f" · {r['cursor']:,} / {r['total']:,} · {r['imported']:,} imported · {r['duplicates']:,} duplicates · {r['unresolved']:,} need match · {r['invalid']:,} invalid")
            if r['status'] in ('PENDING','RUNNING'):state().setdefault('activity',{})['imports']='LOADING'
        completed=tuple((str(r['id']),r['cursor']) for r in jobs if r['status']=='COMPLETED')
        if completed!=state().get('completed_imports',()):
            state()['completed_imports']=completed
            changed('table','summary','sources')
    if activity=='ERROR':st.caption('Import history could not refresh.')

@st.fragment
def display(store,user,navigate):
    settings,activity=load(('settings',),store.settings)
    if settings is None:st.caption('Loading display settings…' if activity!='ERROR' else 'Display settings unavailable.');return
    st.subheader('Shopify display');st.caption('Three app blocks: Product reviews · Review stars · All reviews. Storefront installation is not verified from this page.')
    import os
    shop=os.getenv('SHOPIFY_STORE_DOMAIN','')
    if shop.endswith('.myshopify.com'):st.link_button('Open Shopify Theme Editor','https://'+shop+'/admin/themes/current/editor')
    st.caption('After releasing the extension, add its blocks in Theme Editor. Place All reviews on a normal Shopify page such as /pages/reviews. Set the public Reviews API URL in each block.')
    with st.form('reviews_display_settings'):
        enabled=st.toggle('Enable published storefront data',value=settings['enabled'])
        a,b=st.columns(2)
        value=deepcopy(settings)
        for column,field,label in ((a,'verified','Show verified purchase'),(a,'date','Show review date'),(b,'thumbnail','Show product thumbnail'),(b,'reply','Show merchant reply')):
            value[field]=column.checkbox(label,value=settings[field])
        value['per_page']=a.number_input('Reviews per page',4,20,settings['per_page'])
        value['sort']=b.selectbox('Default sort',['newest','highest','lowest'],index=['newest','highest','lowest'].index(settings['sort']))
        value['accent']=a.color_picker('Accent colour',settings['accent']);value['density']=b.selectbox('Spacing',['compact','comfortable'],index=['compact','comfortable'].index(settings['density']))
        value['moderation']=st.selectbox('New Sports Cave reviews',['manual','publish_all'],index=['manual','publish_all'].index(settings['moderation']),format_func=lambda v:'Manual moderation · every rating' if v=='manual' else 'Publish every rating')
        if st.form_submit_button('Save display settings',type='primary'):
            value['enabled']=enabled;store.save_settings(user,value);changed('settings');st.toast('Display settings saved')
    import os_accounts
    if os_accounts.can_access_page(user,'crm_automations_manage'):
        with st.expander('Review-request automation'):
            query=st.text_input('Find purchased product',key='review_request_product_search')
            choices,_=load(('products',query),lambda:store.products(query))
            if choices:
                product=st.selectbox('Product',choices,format_func=lambda p:p['title'],key='review_request_product')
                days=st.number_input('Days after fulfilment',1,90,7)
                if st.button('Create review-request automation'):
                    from reviews_submission import create_automation
                    row=create_automation(user,store,product['shopify_product_id'],days)
                    st.session_state['automation_selected']=str(row['id']);st.session_state.pop('automation_editor',None)
                    st.query_params['automation']=str(row['id']);navigate('CRM Automations')
            st.caption('Opens the existing Email Automation editor as a draft. Publishing and delivery keep the existing consent and send guards.')

def render_page(user,navigate=lambda _:None,*,store=None):
    require(user);store=store or ReviewsStore()
    st.html(STYLE+STYLE_REVIEW)
    with st.container(key='sc-reviews'):
        st.title('Reviews');st.caption('Manage customer reviews and storefront social proof.')
        tab=st.segmented_control('Reviews area',['Overview','Import reviews','Display'],default='Overview',key='reviews-tabs') or 'Overview'
        state()['activity']={}
        try:
            if tab=='Overview':overview(store,user)
            elif tab=='Import reviews':importer(store,user)
            else:display(store,user,navigate)
        except (ValueError,PermissionError) as exc:st.warning(str(exc))
        except Exception:st.warning('Reviews could not complete this operation. Retry when storage is available.')
        with st.container(key='reviews-poll'):
            if st.button('Refresh reviews',key='reviews-refresh'):pass
        if any(a in ('LOADING','REFRESHING') for a in state().get('activity',{}).values()):
            # One controller, active only for pending reads/imports. No provider polling.
            st.html('<script>setTimeout(()=>{if(!document.hidden&&!document.querySelector("[role=dialog]"))document.querySelector(".st-key-reviews-poll button")?.click()},1200)</script>',unsafe_allow_javascript=True)
