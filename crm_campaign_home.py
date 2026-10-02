"""Campaigns Home: presentation and navigation over existing authoring contracts."""
from html import escape
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from time import monotonic, perf_counter
import logging
import streamlit as st
from crm_campaign_home_data import summary, top_identity, rows, invalidate, TTL, PAGE_SIZE
from crm_campaign_analytics import money
from crm_catalogue import picker_thumbnail
from crm_store import StoreUnavailable

POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='campaign-home')
CAPACITY = BoundedSemaphore(8)
TABS = ('All campaigns','Drafts','Active','Sent','Archived')


def _job(state, store, key, load):
    cache = state.setdefault('campaign_home_cache', {})
    identity = (store.connect,key)
    entry = cache.get(identity)
    if entry and (not entry[1].done() or monotonic()-entry[0]<TTL): return entry[1]
    if not CAPACITY.acquire(blocking=False): return None
    def work():
        started=perf_counter()
        try: return load()
        finally:
            logging.getLogger(__name__).info('campaign_home stage=%s duration_ms=%.1f',key[0],(perf_counter()-started)*1000)
            CAPACITY.release()
    if len(cache)>=8: cache.clear()
    future=POOL.submit(work)
    cache[identity]=(monotonic(),future)
    return future


def request_open(identity, *, templates=False):
    invalidate(st.session_state)
    st.session_state['campaign_pending_open']=identity
    if templates: st.session_state['campaign_open_templates']=True
    st.rerun()


def return_home():
    invalidate(st.session_state)
    st.session_state['campaign_view']='CAMPAIGNS_HOME'
    st.session_state.pop('campaign_recovery_context',None)
    st.query_params.pop('campaign',None)


STYLE = '''<style>
 [data-testid="stMainBlockContainer"]:has(.st-key-crm-campaign-home){max-width:none;padding:calc(var(--sc-topbar-height,64px) + 18px) 24px 20px!important}
 .st-key-crm-campaign-home{color:#161820}
 .st-key-crm-campaign-home h1{font-size:30px;margin:0;line-height:1.2}
 .st-key-crm-campaign-home p{margin-bottom:3px}
 .st-key-crm-campaign-home [data-testid="stVerticalBlock"]{gap:10px}
 .sc-home-breadcrumb{font-size:13px;color:#777}.sc-home-breadcrumb span{color:#ae8422}
 .sc-home-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
 .sc-home-kpi{display:flex;gap:12px;border:1px solid #e9e6e0;border-radius:10px;padding:16px 12px;background:#fff;min-width:0}
 .sc-home-icon{background:#f7f1e4;color:#b48e32;border-radius:8px;padding:8px;height:38px;font-size:20px}
 .sc-home-kpi small{display:block;color:#73747c;font-size:11px}.sc-home-kpi strong{display:block;font-size:22px;line-height:1.5;overflow-wrap:anywhere}
 .st-key-crm-home-main,.st-key-crm-home-rail>div{min-width:0}
 .st-key-crm-home-list{border:1px solid #e9e6e0;border-radius:10px;background:#fff;padding:12px}
 .st-key-crm-home-table{overflow-x:auto}
 .st-key-crm-campaign-home button[kind="secondary"]{background:#fff!important;color:#242424!important;border:1px solid #e5e1d8!important}
 .st-key-crm-home-tabs label[data-baseweb="radio"]>div:first-child{display:none}
 .st-key-crm-home-tabs [role="radiogroup"]{gap:14px;flex-wrap:wrap}
 .st-key-crm-home-tabs [data-testid="stRadio"] label{font-size:12px}
 .st-key-crm-home-tabs label:has(input:checked){border-bottom:2px solid #c7a13f;padding-bottom:6px}
 .st-key-crm-home-controls button p{white-space:nowrap}
 .sc-home-table-head,.sc-home-row{display:grid;grid-template-columns:minmax(215px,2.8fr) 48px 96px repeat(4,minmax(62px,.8fr)) 50px minmax(86px,1fr) 78px;gap:8px;align-items:center;min-width:970px}
 .sc-home-table-head{font-size:10px;color:#818178;padding:10px 0;border-bottom:1px solid #eee}
 .sc-home-row{font-size:12px;padding:10px 0;border-bottom:1px solid #eee}
 .sc-home-row small{display:block;color:#777;font-size:11px;margin-top:3px}
 .sc-home-identity{display:flex;align-items:center;gap:10px;min-width:0}
 .sc-home-identity a{color:#171820;text-decoration:none}.sc-home-identity a:hover{text-decoration:underline}
 .sc-home-thumb{width:62px;height:62px;object-fit:contain;border-radius:5px;background:#f6f3ec;flex-shrink:0}
 .sc-home-placeholder{display:grid;place-items:center;font-size:26px;color:#b48e32}
 .sc-home-pill{padding:4px 7px;border-radius:6px;background:#f3f3f0;font-size:11px}
 .sc-home-pill.sent{background:#edf6ee;color:#28763a}.sc-home-pill.draft{background:#edf3fa;color:#396796}
 .st-key-crm-home-table [data-testid="stHorizontalBlock"]{min-width:1045px;flex-wrap:nowrap;gap:8px}
 .st-key-crm-home-list [data-testid="stColumn"]{min-width:0}
 .st-key-crm-home-list [data-testid="stPopover"] button{font-size:12px;padding:4px 8px;min-height:30px}
 .st-key-crm-home-list [data-testid="stPopover"] button p{white-space:nowrap}
 .st-key-crm-home-rail [data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-color:#e9e6e0;border-radius:10px}
 .sc-home-banner{border:1px solid #eee4ce;border-radius:10px;padding:16px;font-size:13px;background:#fcfaf5}
 .sc-home-banner strong{display:block}.sc-home-banner small{color:#777}
 @media(max-width:1500px){.sc-home-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
 @media(max-width:1500px){.st-key-crm-home-layout>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{flex-wrap:wrap}
 .st-key-crm-home-layout>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important}
 .st-key-crm-home-toolbar>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{flex-wrap:wrap}
 .st-key-crm-home-toolbar>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100%!important;flex:1 1 100%!important}}
 @media(max-width:1200px){.sc-home-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
 @media(max-width:700px){.sc-home-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.sc-home-kpi{padding:10px;gap:8px}
 .st-key-crm-home-controls [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
 .st-key-crm-home-controls [data-testid="stColumn"]{flex:1 1 45%;min-width:0}
 .st-key-crm-campaign-home h1{font-size:25px}}
 </style>'''


def kpis(data=None):
    data=data or {}
    def number(key): return format(data[key],',') if data.get(key) is not None else '—'
    values=(('✉','Active',number('active'),'campaigns'),('↗','Sent (30 days)',number('sent_emails'),'emails submitted'),
      ('▥','Revenue (30 days)',money(data.get('revenue') or {}),''),
      ('↖','Click rate (avg · 30 days)',format(float(data['click_rate']),'.1f')+'%' if data.get('click_rate') is not None else '—',''),
      ('▱','Orders from email (30 days)',number('orders'),''))
    return '<div class="sc-home-kpis">'+''.join('<div class="sc-home-kpi"><span class="sc-home-icon" aria-hidden="true">'+icon+'</span><div><small>'+escape(label)+'</small><strong>'+escape(value)+'</strong><small>'+escape(note)+'</small></div></div>' for icon,label,value,note in values)+'</div>'


def thumbnail(row):
    url=picker_thumbnail(row.get('thumbnail') or '')
    return '<img class="sc-home-thumb" src="'+escape(url,quote=True)+'" alt="'+escape(row['name'],quote=True)+'" loading="lazy">' if url else '<span class="sc-home-thumb sc-home-placeholder" aria-hidden="true">SC</span>'


def row_html(row):
    from crm_logic import date
    stamp=date(row['updated_at']) if row.get('updated_at') else None
    def metric(field, rate_field=None):
        value=row.get(field)
        return ('—' if value is None else format(value,','))+('<small>'+str(row[rate_field])+'%</small>' if rate_field and row.get(rate_field) is not None else '')
    status='Archived' if row.get('archived_at') else {'DRAFT':'Draft','NEEDS_REVIEW':'Draft','TEST_READY':'Draft','BUILDING':'Active'}.get(row['status'],row['status'].title())
    destination='?'+urlencode({'page':'CRM Campaigns','campaign':str(row['id'])})
    cells=['<div class="sc-home-identity">'+thumbnail(row)+'<div><a href="'+escape(destination,quote=True)+'" target="_self"><strong>'+escape(row['name'])+'</strong></a><small>'+escape(row.get('subject') or '')+'</small></div></div>',
      escape(row.get('market') or '—'),stamp.strftime('%d %b %Y')+'<small>'+stamp.strftime('%H:%M UTC')+'</small>' if stamp else '—',
      metric('recipients'),metric('delivered','delivery_rate'),metric('opens','open_rate'),metric('clicks','click_rate'),metric('orders'),
      escape(money(row.get('revenue') or {})), '<span class="sc-home-pill '+status.lower()+'">'+escape(status)+'</span>']
    return '<div class="sc-home-row">'+''.join('<div>'+value+'</div>' for value in cells)+'</div>'


def actions(store,user,row):
    from crm_campaign_page import open_editor,delete_dialog
    identity=str(row['id'])
    with st.popover('Actions',help='Actions for '+row['name']):
        if st.button('View campaign' if row.get('delivery_status') else 'Edit',key='home_open_'+identity):request_open(identity)
        if st.button('Duplicate',key='home_duplicate_'+identity):
            invalidate(st.session_state);open_editor(store.duplicate(user,identity));st.rerun()
        if row.get('delivery_status')=='SENT' and st.button('View results',key='home_results_'+identity):
            st.session_state['sent_analytics_id']=identity;st.rerun(scope='fragment')
        if st.button('History',key='home_history_'+identity):st.session_state['campaign_revision_history_id']=identity
        if st.session_state.get('campaign_revision_history_id')==identity:st.dataframe(store.history(identity),hide_index=True)
        if not row.get('delivery_status') or row['delivery_status']=='SENT':
            if st.button('Restore' if row['archived_at'] else 'Archive',key='home_archive_'+identity):
                (store.restore if row['archived_at'] else store.archive)(user,identity,row['version']);invalidate(st.session_state);st.rerun(scope='fragment')
        deletable=row['draft_status']=='DRAFT' and not row['archived_at'] and not row['last_tested_at'] and not row.get('delivery_status')
        if deletable and st.button('Delete draft',key='home_delete_'+identity):
            st.session_state['campaign_delete_dialog_id']=identity;st.rerun(scope='fragment')


@st.fragment
def home(store,user):
    # All slots and all later replacements belong to this one fragment.
    st.html(STYLE)
    with st.container(key='crm-campaign-home'):
        st.html('<div class="sc-home-breadcrumb"><span>Email</span> › Campaigns</div>')
        title,new=st.columns([4,1],vertical_alignment='center')
        title.html('<h1>Campaigns</h1><p style="color:#73747c">Create, review and send email campaigns.</p>')
        if new.button('+ New campaign',type='primary',use_container_width=True,key='home_new'):request_open('new')
        with st.container(key='crm-home-layout'):
            main,rail=st.columns([4,1.08],gap='medium')
        with main,st.container(key='crm-home-main'):
            metric_slot=st.empty();metric_slot.html(kpis())
            with st.container(key='crm-home-list'):
                with st.container(key='crm-home-toolbar'):
                    tabs_col,controls_col=st.columns([5,4],vertical_alignment='center')
                with tabs_col,st.container(key='crm-home-tabs'):
                    counts=st.session_state.get('campaign_home_counts') or {}
                    tab=st.radio('Campaign view',TABS,horizontal=True,label_visibility='collapsed',key='campaign_home_tab',
                        format_func=lambda t:t+'  '+str(counts.get({'All campaigns':'all_count','Drafts':'drafts','Active':'active','Sent':'sent','Archived':'archived'}[t],'—')))
                with controls_col,st.container(key='crm-home-controls'):
                    search_col,filter_col,sort_col=st.columns([3,1,1.6])
                    search=search_col.text_input('Search campaigns',placeholder='Search campaigns…',label_visibility='collapsed',key='campaign_home_search',max_chars=150)
                    with filter_col.popover('Filter'):
                        from crm_campaign_content import MARKETS
                        market=st.selectbox('Market',('All',*MARKETS),key='campaign_home_market')
                        status=st.selectbox('Status',('All','DRAFT','NEEDS_REVIEW','TEST_READY','BUILDING','SCHEDULED','SENDING','SENT','PAUSED','CANCELLED'),key='campaign_home_status')
                    sort=sort_col.selectbox('Sort',('Newest first','Oldest first'),label_visibility='collapsed',key='campaign_home_sort')
                filters=(tab,search,market,status,sort)
                if st.session_state.get('campaign_home_filters')!=filters:
                    st.session_state['campaign_home_filters']=filters;st.session_state['campaign_home_offset']=0
                offset=st.session_state.get('campaign_home_offset',0)
                with st.container(key='crm-home-table'):
                    left,menu=st.columns([14,1.4])
                    left.html('<div class="sc-home-table-head">'+''.join('<span>'+label+'</span>' for label in ('CAMPAIGN','MARKET','UPDATED','RECIPIENTS','DELIVERED','OPENED','CLICKED','ORDERS','REVENUE','STATUS'))+'</div>')
                    menu.caption('ACTIONS')
                    table_slot=st.empty()
            with st.container(horizontal=True):
                st.html('<div class="sc-home-banner"><strong>Turn collectors into lifelong fans.</strong><small>Share new releases, tell the stories, and grow your community with powerful email campaigns.</small></div>')
                if st.button('Browse templates',key='home_banner_templates'):request_open('new',templates=True)
        with rail,st.container(key='crm-home-rail'):
            with st.container(border=True):
                st.markdown('**Quick actions**')
                if st.button('+ Create campaign',type='primary',use_container_width=True,key='home_create'):request_open('new')
                duplicate_slot=st.empty()
                if st.button('View email templates',use_container_width=True,key='home_templates'):request_open('new',templates=True)
            with st.container(border=True):
                st.markdown('**Top performing campaign**')
                top_slot=st.empty();top_slot.caption('No performance data yet.')
        # Shell, controls, headers and rail have all been emitted before reads start.
        stats_job=_job(st.session_state,store,('summary',),lambda:summary(store))
        detail=st.session_state.get('sent_analytics_id')
        def load_table():
            top=top_identity(store)
            return top,rows(store,tab=tab,search=search,market=market,status=status,oldest=sort=='Oldest first',offset=offset,top=top,detail=detail)
        table_job=_job(st.session_state,store,('table',filters,offset,detail),load_table)
        pending=False
        if stats_job and stats_job.done():
            try:
                stats=stats_job.result();metric_slot.html(kpis(stats))
                if counts!=stats:pending=True
                st.session_state['campaign_home_counts']=stats
            except StoreUnavailable:
                with metric_slot.container():
                    st.html(kpis())
                    st.caption('Campaign totals temporarily unavailable.')
        else:pending=True
        if table_job and table_job.done():
            try:
                top_id,items=table_job.result()
                page=[r for r in items if r['in_page']]
                with table_slot.container():
                    if not page:st.caption('No campaigns match these filters.')
                    for row in page[:PAGE_SIZE]:
                        content,menu=st.columns([14,1.4],vertical_alignment='center')
                        content.html(row_html(row))
                        with menu:actions(store,user,row)
                    if offset or len(page)>PAGE_SIZE:
                        prev,next_=st.columns(2)
                        if prev.button('Previous',disabled=offset==0,key='home_prev'):
                            st.session_state['campaign_home_offset']=max(0,offset-PAGE_SIZE);st.rerun(scope='fragment')
                        if next_.button('Next',disabled=len(page)<=PAGE_SIZE,key='home_next'):
                            st.session_state['campaign_home_offset']=offset+PAGE_SIZE;st.rerun(scope='fragment')
                top=next((r for r in items if str(r['id'])==top_id),None)
                if top:
                    with top_slot.container():
                        st.html('<div class="sc-home-identity">'+thumbnail(top)+'<strong>'+escape(top['name'])+'</strong></div>')
                        st.caption('Ranked by attributed orders · all time')
                        if top.get('sent_at'):st.caption('Sent '+str(top['sent_at'])[:10])
                        for label,field in (('Open rate','open_rate'),('Click rate','click_rate')):
                            st.caption(label+' · '+(str(top[field])+'%' if top[field] is not None else '—'))
                        st.caption('Orders · '+str(top['orders']));st.caption('Revenue · '+money(top['revenue']))
                        if st.button('View campaign',key='home_top_view',use_container_width=True):request_open(top_id)
                    with duplicate_slot.container():
                        if st.button('Duplicate top performer',key='home_top_duplicate',use_container_width=True):
                            from crm_campaign_page import open_editor
                            invalidate(st.session_state);open_editor(store.duplicate(user,top_id));st.rerun()
                selected=next((r for r in items if str(r['id'])==st.session_state.get('campaign_delete_dialog_id')),None)
                if selected:
                    from crm_campaign_page import delete_dialog
                    delete_dialog(store,user,selected)
                selected=next((r for r in items if str(r['id'])==st.session_state.get('sent_analytics_id')),None)
                if selected:
                    from crm_campaign_analytics_ui import analytics
                    analytics(store,user,selected)
            except StoreUnavailable:table_slot.caption('Campaign list temporarily unavailable.')
        else:pending=True;table_slot.caption('Loading campaigns…')
        from crm_campaign_progress_ui import poll
        if not st.session_state.get('sent_analytics_id') and not st.session_state.get('campaign_delete_dialog_id'):
            if poll('crm-home-poll',.3 if pending else TTL):
                if not pending:invalidate(st.session_state)
                st.rerun(scope='fragment')
        elif pending:
            # A directly opened analytics row can be outside the current page.
            # Resolve it before opening the dialog; once open, suspend polling.
            poll('crm-home-detail-poll',.3)
