"""Campaigns Home: presentation and navigation over existing authoring contracts."""
from html import escape
from base64 import b64encode
from urllib.parse import urlencode
from time import monotonic
from uuid import uuid4
import streamlit as st
from crm_campaign_home_data import counts, delivery_summary, orders_summary, reporting_window, rows, invalidate, TTL, PAGE_SIZE
from crm_campaign_home_cache import job as _job, resolve
from crm_campaign_delete import remove_cached_row, delete_campaign
from crm_catalogue import picker_thumbnail

TABS = ('All campaigns','Drafts','Active','Sent','Archived')
FIELDS = ('campaign','market','updated','recipients','delivered','opened','clicked','orders','status')


def refresh_delay():
    states=st.session_state.get('campaign_home_activity',{}).values()
    from crm_campaign_progress import POLL_SECONDS
    return .25 if any(s in ('UNRESOLVED','LOADING','REFRESHING') for s in states) else POLL_SECONDS if st.session_state.get('campaign_home_dispatch_active') else TTL


def arm_home_poll():
    """One read-only parent refresh event; child interactions may accelerate it.

    No external Streamlit container mutation and no redundant explicit rerun.
    One-shot scheduling waits for each render to complete before the next event.
    """
    if st.session_state.get('campaign_home_rendering'): return
    key='crm-home-poll';seconds=refresh_delay()
    # A unique script token re-arms identical pending-delay scripts in Streamlit.
    st.html('<script>/* '+uuid4().hex+' */'+
        '(()=>{const key='+repr(key)+';const delay='+str(int(seconds*1000))+';'+
        'window.scCampaignTimers??={};clearTimeout(window.scCampaignTimers[key]);'+
        'const tick=()=>{const b=document.querySelector(".st-key-"+key+" button");'+
        'if(!b||!b.isConnected)return;'+
        'if(document.hidden){window.scCampaignTimers[key]=setTimeout(tick,30000);return;}'+
        'if(b.disabled||document.querySelector("[role=dialog]")){window.scCampaignTimers[key]=setTimeout(tick,delay);return;}b.click();};'+
        'window.scCampaignTimers[key]=setTimeout(tick,delay);})();</script>',unsafe_allow_javascript=True)


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
 [data-testid="stMainBlockContainer"]:has(.st-key-crm-campaign-home){max-width:none;padding:calc(var(--sc-topbar-height,64px) + 20px) 24px 20px!important}
 .st-key-crm-campaign-home{color:#161820;margin-top:-32px;font-family:Arial,sans-serif}
 .st-key-crm-campaign-home h1{font-size:30px;margin:0;line-height:1.2}
 .st-key-crm-campaign-home p{margin-bottom:3px}
 .st-key-crm-campaign-home [data-testid="stVerticalBlock"]{gap:8px}
 .sc-home-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
 .sc-home-kpi{display:flex;align-items:center;gap:10px;border:1px solid #e9e6e0;border-radius:12px;padding:14px 12px;background:#fff;min-width:0;min-height:92px;box-sizing:border-box}
 .sc-home-icon{display:grid;place-items:center;flex:none;border-radius:9px;width:36px;height:36px;color:#947021;background:#faf3df}
 .sc-home-icon img{width:21px;height:21px}
 .sc-home-icon.green{color:#218148;background:#e9f6ee}.sc-home-icon.blue{color:#2380b5;background:#eaf4fd}
 .sc-home-icon.purple{color:#8058ad;background:#f3edfa}.sc-home-icon.rose{color:#af5268;background:#fbeef1}
 .sc-home-kpi small{display:block;color:#73747c;font-size:11px}.sc-home-kpi strong{display:block;font-size:22px;line-height:1.5;overflow-wrap:anywhere;min-height:33px;font-variant-numeric:tabular-nums}
 .sc-home-unresolved{display:block;width:65px;height:22px;margin:5px 0;background:#efeeeb;border-radius:4px}
 .st-key-crm-home-list{border:1px solid #e9e6e0;border-radius:12px;background:#fff;padding:12px;min-width:0;container-type:inline-size}
 .st-key-crm-campaign-home button[kind="secondary"]{background:#fff!important;color:#242424!important;border:1px solid #e5e1d8!important}
 .st-key-crm-home-tabs button{border:0!important;border-radius:0!important;background:transparent!important;color:#64646c!important;box-shadow:none!important;padding:9px 10px!important;border-bottom:2px solid transparent!important}
 .st-key-crm-home-tabs button[kind="segmented_controlActive"]{color:#181818!important;border-bottom-color:#c7a13f!important;font-weight:600}
 .st-key-crm-home-tabs [data-testid="stWidgetLabel"]{display:none}
 .st-key-crm-home-tabs button:focus-visible{outline:2px solid #b99232!important;outline-offset:2px}
 .st-key-crm-home-controls button p{white-space:nowrap}
 .st-key-crm-home-controls [data-baseweb="input"]:focus-within{border-color:#c7a13f!important;box-shadow:0 0 0 1px #c7a13f!important}
 .sc-home-table-head,.sc-home-row{display:grid;grid-template-columns:minmax(180px,2.8fr) 42px 82px repeat(4,minmax(45px,.65fr)) 40px 75px;gap:7px;align-items:center;min-width:0}
 .sc-home-table-head{font-size:10px;color:#818178;padding:10px 0;border-bottom:1px solid #eee}
 .sc-home-row{font-size:12px;padding:12px 0;border-bottom:1px solid #eee;font-variant-numeric:tabular-nums}
 .sc-home-row:hover{background:#fcfbf7}.sc-home-row>div{min-width:0;overflow-wrap:anywhere}
 .sc-col-recipients,.sc-col-delivered,.sc-col-opened,.sc-col-clicked,.sc-col-orders{text-align:right}
 .sc-home-row small{display:block;color:#777;font-size:11px;margin-top:3px}
 .sc-home-identity{display:flex;align-items:center;gap:10px;min-width:0}
 .sc-home-identity a{color:#171820;text-decoration:none}.sc-home-identity a:hover{text-decoration:underline}
 .sc-home-thumb{width:52px;height:52px;object-fit:contain;border-radius:5px;background:#f6f3ec;flex-shrink:0}
 .sc-home-placeholder{display:grid;place-items:center;font-size:22px;color:#b48e32}
 .sc-home-pill{display:inline-block;padding:4px 7px;border-radius:6px;background:#f3f3f0;font-size:11px;white-space:nowrap}
 .sc-home-pill.sent,.sc-home-pill.active,.sc-home-pill.sending,.sc-home-pill.scheduled{background:#edf6ee;color:#28763a}.sc-home-pill.draft{background:#edf3fa;color:#396796}
 .sc-col-status .sc-home-pill{white-space:normal;max-width:100%;box-sizing:border-box}
 .sc-home-pill.stalled,.sc-home-pill.failed,.sc-home-pill.needs{background:#fff4e7;color:#8a5021}
 .sc-home-send-bar{height:4px;background:#eee9df;margin-top:4px;border-radius:2px;overflow:hidden}.sc-home-send-bar span{display:block;height:100%;background:#bc9639}
 .st-key-crm-home-table [data-testid="stHorizontalBlock"]{flex-wrap:nowrap;gap:8px}
 .st-key-crm-home-table [data-testid="stColumn"]{min-width:0}
 .st-key-crm-home-table [data-testid="stColumn"]:last-child{flex:0 0 76px!important;width:76px!important}
 .st-key-crm-home-table [data-testid="stColumn"]:first-child{flex:1 1 0!important}
 .st-key-crm-home-list [data-testid="stPopover"] button{font-size:12px;padding:4px 8px;min-height:36px}
 .st-key-crm-home-table [data-testid="stPopover"] button p{font-size:0}
 .st-key-crm-home-table [data-testid="stPopover"] button p::after{content:"⋯";font-size:18px}
 .st-key-crm-home-table [data-testid="stPopover"] button svg{display:none}
 .st-key-crm-home-table [class*="st-key-home_delete_"] button{min-width:36px;min-height:40px;padding:4px!important}
 .st-key-crm-home-table [class*="st-key-home_delete_"] button p{font-size:0}
 .sc-home-actions-label{font-size:8px;color:#818178;padding-top:10px;text-align:center}
 .sc-home-mobile-summary{display:none!important}
 @container(max-width:920px){.sc-home-table-head,.sc-home-row{grid-template-columns:minmax(180px,2.8fr) 42px 82px repeat(3,minmax(45px,.65fr)) 75px}.sc-col-opened,.sc-col-orders{display:none}}
 @container(max-width:720px){.sc-home-table-head,.sc-home-row{grid-template-columns:minmax(160px,2.8fr) 42px repeat(2,minmax(45px,.65fr)) 65px}.sc-col-updated,.sc-col-delivered{display:none}}
 @container(max-width:520px){.sc-home-table-head,.sc-home-row{grid-template-columns:minmax(0,1fr) 32px 58px;gap:5px}.sc-col-recipients,.sc-col-clicked{display:none}.sc-home-mobile-summary{display:block!important}.sc-home-thumb{width:40px;height:40px}.sc-home-identity{gap:6px}}
 @media(max-width:1500px){.sc-home-kpi{gap:8px;padding:12px 10px}}
 @media(max-width:1200px){.sc-home-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
 @media(max-width:700px){.sc-home-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.sc-home-kpi{padding:10px;gap:8px}
 .st-key-crm-home-controls [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
 .st-key-crm-home-controls [data-testid="stColumn"]:first-child{flex:1 1 100%!important;width:100%!important}
 .st-key-crm-home-controls [data-testid="stColumn"]{flex:1 1 40%!important;min-width:0}
 .st-key-crm-campaign-home h1{font-size:25px}
 [data-testid="stMainBlockContainer"]:has(.st-key-crm-campaign-home){padding-left:12px!important;padding-right:12px!important}}
 </style>'''

# Lucide outline glyphs, matching the existing application's simple line icons.
# Fixed system-owned paths; no font/API dependency or arbitrary user SVG.
ICON_PATHS = (
 '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 6-10 7L2 6"/>',
 '<path d="m22 2-7 20-4-9-9-4Z M22 2 11 13"/>',
 '<path d="M9 10 5 6 1 10 M5 6v8a4 4 0 0 0 4 4h4"/><rect x="13" y="3" width="9" height="13" rx="2"/><path d="M17.5 7v3 M17.5 13h.01"/>',
 '<path d="m3 3 7 18 2-7 7-2Z M14 14l7 7"/>',
 '<path d="M2 3h2l3 12h12l3-8H5"/><circle cx="9" cy="20" r="1"/><circle cx="19" cy="20" r="1"/>')


def kpis(data=None):
    data=data or {}
    def number(key): return format(data[key],',') if data.get(key) is not None else '—'
    values=(('green','Active',number('active'),'campaigns','active'),('blue','Sent (30 days)',number('sent_emails'),'emails submitted','sent_emails'),
      ('gold','Bounce rate (30 days)',format(float(data['bounce_rate']),'.1f')+'%' if data.get('bounce_rate') is not None else '—','','bounce_rate'),
      ('purple','Click rate (avg · 30 days)',format(float(data['click_rate']),'.1f')+'%' if data.get('click_rate') is not None else '—','','click_rate'),
      ('rose','Orders (30 days)',number('orders'),'from email','orders'))
    cards=[]
    for paths,(colour,label,value,note,key) in zip(ICON_PATHS,values):
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+paths+'</svg>'
        icon='<img src="data:image/svg+xml;base64,'+b64encode(svg.replace('currentColor',{'green':'#218148','blue':'#2380b5','gold':'#947021','purple':'#8058ad','rose':'#af5268'}[colour]).encode()).decode()+'" width="21" height="21" alt="">'
        displayed=escape(value) if key in data else '<span class="sc-home-unresolved" aria-label="Not yet loaded"></span>'
        cards.append('<div class="sc-home-kpi"><span class="sc-home-icon '+colour+'" aria-hidden="true">'+icon+'</span><div><small>'+escape(label)+'</small><strong>'+displayed+'</strong><small>'+escape(note)+'</small></div></div>')
    return '<div class="sc-home-kpis">'+''.join(cards)+'</div>'


def thumbnail(row):
    url=picker_thumbnail(row.get('thumbnail') or '')
    return '<img class="sc-home-thumb" src="'+escape(url,quote=True)+'" alt="'+escape(row['name'],quote=True)+'" loading="lazy" width="52" height="52">' if url else '<span class="sc-home-thumb sc-home-placeholder" aria-hidden="true">SC</span>'


def row_html(row):
    from crm_logic import date
    stamp=date(row['updated_at']) if row.get('updated_at') else None
    def metric(field, rate_field=None):
        value=row.get(field)
        return ('—' if value is None else format(value,','))+('<small>'+str(row[rate_field])+'%</small>' if rate_field and row.get(rate_field) is not None else '')
    status='Archived' if row.get('archived_at') else {'DRAFT':'Draft','NEEDS_REVIEW':'Draft','TEST_READY':'Draft','BUILDING':'Active'}.get(row['status'],row['status'].title())
    destination='?'+urlencode({'page':'CRM Campaigns','campaign':str(row['id'])})
    submission=('<small>'+format(row['submitted'],',')+' / '+format(row['planned'],',')+' submitted</small>') if row['status']=='SENDING' and row.get('submitted') is not None and row.get('planned') is not None else ''
    progress=row.get('progress')
    if progress:
        detail=' · '.join(str(progress[f])+' '+f for f in ('submitted','skipped','failed','held'))
        if progress.get('stalled'):status='Stalled'
        elif progress['held']:status='Needs attention'
        elif progress['complete'] and progress['failed']:status='Sent with issues'
        elif row['status']=='SENDING' and not progress.get('worker_started_at') and not progress['processed']:status='Queued'
        if row['status'] in ('SENDING','QUEUED','BUILDING'):
            submission='<small title="'+escape(detail,quote=True)+'">'+format(progress['processed'],',')+' / '+format(progress['total'],',')+'</small>'
            submission+='<div class="sc-home-send-bar" role="progressbar" aria-label="Campaign processing" aria-valuenow="'+str(progress['processed'])+'" aria-valuemin="0" aria-valuemax="'+str(progress['total'])+'"><span style="width:'+str(progress['percent']*100)+'%"></span></div>'
        else:submission='<small title="'+escape(detail,quote=True)+'">Needs attention</small>' if progress['attention'] else ''
    if row['status']=='SCHEDULED' and (progress or {}).get('scheduled_at'):
        submission='<small>'+escape(date(progress['scheduled_at']).strftime('%d %b %H:%M UTC'))+'</small>'
    cells=['<div class="sc-home-identity">'+thumbnail(row)+'<div><a href="'+escape(destination,quote=True)+'" target="_self"><strong>'+escape(row['name'])+'</strong></a><small>'+escape(row.get('subject') or '')+'</small><small class="sc-home-mobile-summary">'+escape(metric('delivered')+' delivered · '+metric('clicks')+' clicked')+'</small></div></div>',
      escape(row.get('market') or '—'),stamp.strftime('%d %b %Y')+'<small>'+stamp.strftime('%H:%M UTC')+'</small>' if stamp else '—',
      metric('recipients'),metric('delivered','delivery_rate'),metric('opens','open_rate'),metric('clicks','click_rate'),metric('orders'),
      '<span class="sc-home-pill '+status.lower()+'">'+escape(status)+'</span>'+submission]
    return '<div class="sc-home-row">'+''.join('<div class="sc-col-'+field+'">'+value+'</div>' for field,value in zip(FIELDS,cells))+'</div>'


def actions(store,user,row):
    from crm_campaign_page import open_editor
    identity=str(row['id'])
    if row.get('deletable') and st.button('Delete campaign',icon=':material/delete:',help='Delete campaign',key='home_delete_'+identity):
        st.session_state['campaign_home_delete_id']=identity
    with st.popover('Actions for '+row['name']):
        if st.button('View campaign' if row.get('delivery_status') else 'Edit',key='home_open_'+identity):request_open(identity)
        if st.button('Duplicate',key='home_duplicate_'+identity):
            invalidate(st.session_state);open_editor(store.duplicate(user,identity));st.rerun()
        if row.get('delivery_status')=='SENT' and st.button('View results',key='home_results_'+identity):
            request_open(identity)
        if st.button('History',key='home_history_'+identity):st.session_state['campaign_revision_history_id']=identity
        if st.session_state.get('campaign_revision_history_id')==identity:st.dataframe(store.history(identity),hide_index=True)
        if not row.get('delivery_status') or row['delivery_status']=='SENT':
            if st.button('Restore' if row['archived_at'] else 'Archive',key='home_archive_'+identity):
                (store.restore if row['archived_at'] else store.archive)(user,identity,row['version']);invalidate(st.session_state);st.rerun(scope='fragment')
def close_home_delete():
    st.session_state.pop('campaign_home_delete_id',None)


def refresh_after_delete():
    st.html('<script>/* '+uuid4().hex+' */setTimeout(()=>{document.querySelector(".st-key-crm-home-poll button")?.click();},0);</script>',unsafe_allow_javascript=True)


@st.dialog('Delete campaign?',on_dismiss=close_home_delete)
def home_delete_dialog(store,user,row):
    st.write(row['name'])
    st.caption('This removes the campaign from Sports Cave OS. Retained history is preserved.')
    cancel,confirm=st.columns(2)
    if cancel.button('Cancel',key='home_delete_cancel'):
        close_home_delete();refresh_after_delete()
    if confirm.button('Delete',key='home_delete_confirm',type='primary'):
        try: delete_campaign(store,user,str(row['id']),row['version'],confirmed=True)
        except (ValueError,PermissionError) as exc: st.warning(str(exc));return
        except Exception: st.warning('Deletion could not be confirmed. Retry.');return
        remove_cached_row(st.session_state,store,row)
        close_home_delete();refresh_after_delete()


@st.fragment
def metrics(store):
    """Independent KPI region: table interactions cannot reset its values."""
    saved = st.session_state.get('campaign_home_window')
    cache=st.session_state.get('campaign_home_cache',{})
    pending=any(not entry[1].done() for identity,entry in cache.items() if identity[1][0] in ('counts','delivery','attribution'))
    if not saved or monotonic()-saved[0]>=TTL and not pending:
        for name in ('counts','delivery','attribution'): cache.pop((store.connect,(name,)),None)
        saved = (monotonic(), reporting_window())
        st.session_state['campaign_home_window'] = saved
    window = saved[1]
    data = {}; states = []
    for name, fields, load in (
        ('counts', ('all_count','drafts','active','sent','archived'), lambda: counts(store)),
        ('delivery', ('sent_emails','click_rate','bounce_rate'), lambda: delivery_summary(store, window)),
        ('attribution', ('orders',), lambda: orders_summary(store, window))):
        key = (name,)
        future = _job(st.session_state,store,key,load)
        result, status = resolve(st.session_state,store,key,future,fields=fields)
        states.append(status)
        st.session_state.setdefault('campaign_home_activity',{})[name]=status
        if result is not None: data.update(result)
        if name == 'counts' and result is not None:
            st.session_state['campaign_home_counts'] = result
        if status == 'ERROR':
            st.session_state['campaign_home_'+name+'_error'] = True
        else:
            st.session_state.pop('campaign_home_'+name+'_error', None)
    st.html(kpis(data))
    failed = [name for name in ('counts','delivery','attribution') if st.session_state.get('campaign_home_'+name+'_error')]
    if failed:
        st.caption('Some totals are temporarily unavailable · last resolved values retained.')
        if st.button('Retry totals',key='home_retry_totals'):
            for name in failed: st.session_state.get('campaign_home_cache',{}).pop((store.connect,(name,)),None)
            st.rerun(scope='fragment')
    elif 'REFRESHING' in states: st.caption('Refreshing totals…')
    arm_home_poll()


def retain_tab():
    """A selected text tab stays selected when clicked again."""
    tab=st.session_state.get('campaign_home_tab')
    if tab is None:
        st.session_state['campaign_home_tab']=st.session_state.get('campaign_home_last_tab','All campaigns')
    else:
        st.session_state['campaign_home_last_tab']=tab


@st.fragment
def campaign_table(store,user):
    with st.container(key='crm-home-list'):
        with st.container(key='crm-home-tabs'):
            totals=st.session_state.get('campaign_home_counts') or {}
            tab=st.segmented_control('Campaign view',TABS,default='All campaigns',key='campaign_home_tab',on_change=retain_tab,
                format_func=lambda t:t+'  '+str(totals.get({'All campaigns':'all_count','Drafts':'drafts','Active':'active','Sent':'sent','Archived':'archived'}[t],'—')))
            tab=tab or 'All campaigns'
        with st.container(key='crm-home-controls'):
            search_col,filter_col,sort_col=st.columns([6,1.5,2.5],vertical_alignment='center')
            search=search_col.text_input('Search campaigns',placeholder='Search campaigns…',label_visibility='collapsed',key='campaign_home_search',max_chars=150)
            with filter_col.popover('Filter',use_container_width=True,icon=':material/filter_list:'):
                from crm_campaign_content import MARKETS
                market=st.selectbox('Market',('All',*MARKETS),key='campaign_home_market')
                status=st.selectbox('Status',('All','DRAFT','NEEDS_REVIEW','TEST_READY','BUILDING','SCHEDULED','SENDING','SENT','PAUSED','CANCELLED'),key='campaign_home_status')
            sort=sort_col.selectbox('Sort',('Newest first','Oldest first'),label_visibility='collapsed',key='campaign_home_sort')
        filters=(tab,search,market,status,sort)
        if st.session_state.get('campaign_home_filters')!=filters:
            st.session_state['campaign_home_filters']=filters;st.session_state['campaign_home_offset']=0
        offset=st.session_state.get('campaign_home_offset',0)
        key=('table',filters,offset)
        # One bounded projection for this visible tab; no top-performer waterfall.
        future=_job(st.session_state,store,key,lambda:rows(store,tab=tab,search=search,market=market,status=status,oldest=sort=='Oldest first',offset=offset))
        items,state=resolve(st.session_state,store,key,future)
        accepted=st.session_state.get('campaign_home_accepted')
        if accepted and any(str(r['id'])==str(accepted['id']) for r in (items or [])):
            st.session_state.pop('campaign_home_accepted',None)
        elif accepted and filters==('All campaigns','','All','All','Newest first') and offset==0:
            items=[accepted,*(items or [])]
        from crm_campaign_home_progress import live_rows
        if items is not None:items=live_rows(st.session_state,store,items)
        st.session_state.setdefault('campaign_home_activity',{})['table']=state
        with st.container(key='crm-home-table'):
            left,menu=st.columns([30,1],gap='small')
            left.html('<div class="sc-home-table-head">'+''.join('<span class="sc-col-'+field+'">'+label+'</span>' for field,label in zip(FIELDS,('CAMPAIGN','MARKET','UPDATED','RECIPIENTS','DELIVERED','OPENED','CLICKED','ORDERS','STATUS')))+'</div>')
            menu.html('<div class="sc-home-actions-label">ACTIONS</div>')
            page=[r for r in (items or []) if r['in_page']]
            for row in page[:PAGE_SIZE]:
                content,menu=st.columns([30,1],vertical_alignment='center',gap='small')
                content.html(row_html(row))
                with menu:
                    with st.container(horizontal=True,gap='xxsmall'):
                        actions(store,user,row)
            if items is not None and not page:st.caption('No campaigns match these filters.')
            if state=='ERROR':
                st.caption('Campaign list temporarily unavailable · last resolved rows retained.')
                if st.button('Retry list',key='home_retry_list'):
                    st.session_state.get('campaign_home_cache',{}).pop((store.connect,key),None);st.rerun(scope='fragment')
            elif state in ('UNRESOLVED','LOADING','REFRESHING'):st.caption('Loading campaigns…' if items is None else 'Refreshing campaigns…')
            if st.session_state.get('campaign_home_activity',{}).get('progress')=='ERROR':
                st.caption('Live status temporarily unavailable · last recorded progress retained.')
            if offset or len(page)>PAGE_SIZE:
                prev,next_=st.columns(2)
                if prev.button('Previous',disabled=offset==0,key='home_prev'):
                    st.session_state['campaign_home_offset']=max(0,offset-PAGE_SIZE);st.rerun(scope='fragment')
                if next_.button('Next',disabled=len(page)<=PAGE_SIZE,key='home_next'):
                    st.session_state['campaign_home_offset']=offset+PAGE_SIZE;st.rerun(scope='fragment')
        selected=next((r for r in (items or []) if str(r['id'])==st.session_state.get('campaign_home_delete_id')),None)
        if selected: home_delete_dialog(store,user,selected)
        st.html('<script>/* '+uuid4().hex+' */document.querySelectorAll("[class*=st-key-home_delete_] button").forEach(b=>b.setAttribute("aria-label","Delete campaign"));</script>',unsafe_allow_javascript=True)
        arm_home_poll()


@st.fragment
def home(store,user):
    # Each region owns its containers; only the completed parent render arms the
    # shared controller. Child interactions re-arm it when the parent is idle.
    st.session_state['campaign_home_rendering']=True
    try:
        st.html(STYLE)
        notice=st.session_state.pop('campaign_home_notice',None)
        if notice:st.toast(notice,icon=':material/check_circle:')
        with st.container(key='crm-campaign-home'):
            title,new=st.columns([4,1],vertical_alignment='center')
            title.html('<h1>Campaigns</h1><p style="color:#73747c">Create, review and send email campaigns.</p>')
            if new.button('+ New campaign',type='primary',use_container_width=True,key='home_new'):request_open('new')
            metrics(store)
            campaign_table(store,user)
            if st.button('View email templates',key='home_templates',icon=':material/dashboard:'):request_open('new',templates=True)
            with st.container(key='crm-home-poll'):st.button('Refresh campaign data',key='crm-home-poll_tick')
            st.html('<style>.st-key-crm-home-poll{display:none}</style>')
    finally:
        st.session_state['campaign_home_rendering']=False
    arm_home_poll()
