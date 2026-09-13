"""On-demand live Meta review. Saved decisions are optional Supabase context."""
from collections import defaultdict
from contextlib import nullcontext
from html import escape
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import streamlit as st
import meta_ads_client as meta
import meta_review_analysis as analysis
import meta_review_store as store
import meta_review_sync as sync_service
import meta_review_live as live
import meta_review_tables as tables
import meta_review_benchmarks as benchmarks
import meta_review_recency as recency
import meta_review_handoff as handoff
from ads_navigation import CREATIVE_REFRESH_PAGE_KEY, CREATIVE_REFRESH_ROUTE

aggregate_ad_metrics = analysis.aggregate_ad_metrics

def object_dict(value):
    return value if isinstance(value,dict) else {}

@st.cache_data(ttl=60, show_spinner=False)
def _load_preferences(account_id):
    return store.load_preferences(account_id)


def include_unavailable_objects(history):
    """Insights can outlive readable Meta objects. Keep those actual results visible."""
    known={kind:{str(row[kind[:-1]+'_id']) for row in history[kind]} for kind in ('campaigns','adsets','ads')}
    for insight in history['daily']:
        raw=object_dict(insight.get('raw'))
        for kind in ('campaigns','adsets','ads'):
            name=kind[:-1]
            identity=str(insight.get(name+'_id') or raw.get(name+'_id') or '')
            if not identity or identity in known[kind]: continue
            row={name+'_id':identity,name+'_name':insight.get(name+'_name') or raw.get(name+'_name'),
                 'status':'Unavailable','raw':{}}
            if kind=='ads':
                row.update(campaign_id=insight.get('campaign_id') or raw.get('campaign_id'),
                           adset_id=insight.get('adset_id') or raw.get('adset_id'),
                           raw={'creative':raw.get('_review_creative') or {}})
            history[kind].append(row)
            known[kind].add(identity)
    return history


def fmt(value, suffix=''):
    return '—' if value is None else f'{value:,.2f}{suffix}'


def build_ads(history, campaign_id=None, market='All'):
    groups = defaultdict(list)
    for row in history['daily']:
        if not row.get('country') and not row.get('placement'):
            groups[str(row['ad_id'])].append(row)
    creatives = {str(r['creative_id']): r for r in history['creatives']}
    adsets = {str(r['adset_id']): r for r in history['adsets']}
    ads = []
    for row in history['ads']:
        if campaign_id is not None and str(row.get('campaign_id')) != str(campaign_id):
            continue
        adset = adsets.get(str(row.get('adset_id')), {})
        countries = object_dict(object_dict(object_dict(adset.get('raw')).get('targeting')).get('geo_locations')).get('countries') or []
        countries = countries if isinstance(countries,list) else []
        if market != 'All' and market not in countries:
            continue
        raw = (creatives.get(str(row.get('creative_id'))) or {}).get('raw') or (row.get('raw') or {}).get('creative') or {}
        daily = sorted(groups[str(row['ad_id'])], key=lambda r: str(r['date']))
        valid = [r['raw'] if isinstance(r.get('raw'),dict) else {} for r in daily]
        observed = [r['_review_creative'] for r in valid if r.get('_review_creative')]
        if observed:
            raw = observed[-1]
        metrics = analysis.aggregate([analysis.normalize_metrics(r) for r in valid])
        benchmark_metrics=benchmarks.graph_metrics(valid[0] if len(valid)==1 else {},website='country_delivery' in history)
        if 'country_delivery' in history:
            # Live range reports also supply the unchanged winner framework with
            # canonical Graph values; historical helper callers retain their contract.
            metrics={**metrics,**benchmark_metrics}
        country=benchmarks.market([r for r in history.get('country_delivery',[]) if str(r.get('ad_id'))==str(row['ad_id'])])
        midpoint = len(valid)//2
        previous = analysis.aggregate([analysis.normalize_metrics(r) for r in valid[:midpoint]]) if midpoint >= 3 else None
        recent = analysis.aggregate([analysis.normalize_metrics(r) for r in valid[midpoint:]]) if previous else metrics
        ads.append({**row, 'assets': analysis.creative_assets(raw), 'metrics': metrics,
                    'benchmark_metrics':benchmark_metrics,
                    'benchmark':benchmarks.evaluate(benchmark_metrics,benchmarks.ad_format(raw),country,history.get('currency','UNKNOWN')),
                    'adset_name': adset.get('adset_name'), 'markets': countries,
                    'previous': previous, 'recent': recent, 'days': len(valid)})
    peer_groups=defaultdict(list)
    for ad in ads: peer_groups[str(ad.get('campaign_id'))].append(ad['metrics'])
    for ad in ads:
        peers=peer_groups[str(ad.get('campaign_id'))]
        ad['decision'] = analysis.analyse(ad['metrics'], peers)
        fatigue = analysis.analyse(ad['recent'], peers, ad['previous'])
        if fatigue['label'] == 'REFRESH CREATIVE':
            ad['decision'] = fatigue
    return ads


def metrics_card(metrics, compact=False):
    st.dataframe(tables.styled([tables.metrics_row(metrics)]),hide_index=True,width='stretch',placeholder='—',height=72,row_height=30)
    if not compact:
        with st.expander('Funnel and more metrics'):
            labels = [('Add to cart','add_to_cart'),('Cost / ATC','cost_per_atc'),('Initiate checkout','checkout'),
                      ('Cost / checkout','cost_per_checkout'),('Link clicks','inline_link_clicks'),('CTR (all clicks)','click_ctr'),('Outbound clicks','outbound_clicks'),('CPC (all clicks)','cpc'),
                      ('Cost / link click','cost_per_link_click'),('Impressions','impressions'),('Reach (one report only)','reach'),
                      ('Frequency (one report only)','frequency'),('Highest daily frequency','max_daily_frequency'),('CPM','cpm'),
                      ('Engagement','engagement'),('Reactions','reactions'),('Comments','comments'),('Shares','shares'),('Saves','saves'),
                      ('Video views','video_views'),('IE opens','instant_experience_clicks_to_open'),
                      ('IE starts','instant_experience_clicks_to_start'),('IE outbound','instant_experience_outbound_clicks')]
            st.dataframe([{'Metric':label,'Value':fmt(metrics.get(key))} for label,key in labels], hide_index=True, use_container_width=True)
            st.caption('— means unavailable. Reach is not summed across dates or ads. Revenue is Meta-attributed, not Shopify store totals.')


def ad_card(ad):
    with st.container(border=True):
        st.subheader(ad.get('ad_name') or ad['ad_id'])
        st.caption(f"{ad.get('adset_name') or 'Ad set unavailable'} · {ad.get('effective_status') or ad.get('status') or 'Unknown'} · Ad {ad['ad_id']} · Creative {ad['assets']['creative_id']}")
        left, right = st.columns([1,2])
        with left:
            images = ad['assets']['image']
            if images:
                for item in images:
                    st.image(item['value'], caption='Video thumbnail' if item.get('video') else 'Thumbnail' if item.get('thumbnail') else 'Original Meta image', use_container_width=True)
            else:
                st.caption('Original creative image unavailable. No substitute generated.')
        with right:
            for kind, title in (('primary_text','Primary text'),('headline','Headline'),('description','Description'),('cta','CTA'),('url','Destination URL')):
                st.markdown('**'+title+'**')
                for value in ad['assets'][kind]: st.text(value['value'])
                if not ad['assets'][kind]: st.caption('Unavailable')
            if ad['assets']['dynamic'] or ad['assets']['carousel']:
                st.caption('Multiple original assets/cards. Ad-level results do not prove which served combination won.')
        st.caption(f"Ad {ad['ad_id']} · Creative {ad['assets'].get('creative_id') or 'Unavailable'} · Ad set {ad.get('adset_name') or ad.get('adset_id') or 'Unavailable'}")
        with st.expander('Advanced metrics',expanded=False):
            st.dataframe(tables.advanced_rows(ad.get('benchmark_metrics',ad['metrics'])),hide_index=True)


def winner_board(ads, history, context, compact=False):
    if compact:
        return simple_winner(ads,history,context)
    winner = analysis.choose_winner(ads)
    st.markdown('**Sports Cave winner**')
    if winner:
        st.caption('Automatic winning ad: '+str(winner.get('ad_name') or winner['ad_id']))
        if not compact: st.write(winner['decision']['reason'])
    else:
        st.warning('INSUFFICIENT DATA for a trustworthy automatic winner. You can explicitly choose a reference below.')
        leaders = analysis.signal_leaders(ads)
        lower, click = leaders['commercial'], leaders['click']
        if lower:
            (st.caption if compact else st.info)(f"Strongest lower-funnel signal: {lower.get('ad_name') or lower['ad_id']} · "
                f"ATC {fmt(lower['metrics'].get('add_to_cart'))} · Checkout {fmt(lower['metrics'].get('checkout'))}. "
                'Low confidence; needs more spend/data. This is not an established commercial winner.')
        if click:
            (st.caption if compact else st.info)(f"Strongest creative/click signal: {click.get('ad_name') or click['ad_id']} · "
                f"Link CTR {fmt(click['metrics'].get('ctr'), '%')} · Cost/link click {fmt(click['metrics'].get('cost_per_link_click'))}. "
                'Click strength alone does not prove purchase intent. Needs more spend/data.')
    scope = hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()[:12]
    saved = next((row['context'] for row in history['selections'] if row['action_type']=='meta_review_selection' and row['context'].get('scope')==scope), {})
    ids = [str(a['ad_id']) for a in ads]
    by_id = dict(zip(ids, ads))
    overall_options = ['Automatic'] + ids
    default = saved.get('overall', 'Automatic')
    overall = st.selectbox('Overall winning ad', overall_options,
        index=overall_options.index(default) if default in overall_options else 0,
        format_func=lambda key: 'Use automatic winner' if key=='Automatic' else str(by_id[key].get('ad_name') or key), key='review-overall-'+scope)
    selected = winner if overall == 'Automatic' else by_id[overall]
    if not selected: return
    st.caption('Selected reference: '+str(selected.get('ad_name') or selected['ad_id']))
    choices, complete = {}, {}
    component_columns = st.columns(3) if compact else [nullcontext() for _ in range(3)]
    for index, (kind, title) in enumerate((('image','Winning image'),('primary_text','Winning primary text'),('headline','Winning headline'))):
        with component_columns[index]:
            candidates = analysis.component_candidates(ads, kind, history['assets'])
            if not candidates:
                st.warning(title+' unavailable. Handoff requires original image and copy.')
                return
            direct_ads = [{**c,'ad_id':c['key'],'decision':analysis.analyse(c['metrics'], [p['metrics'] for p in candidates])} for c in candidates if c['source']=='DIRECT META ASSET RESULT']
            direct_winner = analysis.choose_winner(direct_ads)
            preferred = next((c for c in candidates if direct_winner and c['key']==direct_winner['key']), None)
            preferred = preferred or next((c for c in candidates if str(c['ad_id'])==str(selected['ad_id'])), candidates[0])
            default_key = saved.get(kind, preferred['key'])
            keys = [c['key'] for c in candidates]
            key = st.selectbox(title, keys, index=keys.index(default_key) if default_key in keys else keys.index(preferred['key']),
                format_func=lambda key, items=tuple(candidates): next((c['value'][:110]+' · Ad '+str(c['ad_id']) for c in items if c['key']==key), str(key)), key='review-'+kind+'-'+scope+'-'+selected['ad_id'])
            choice = next(c for c in candidates if c['key']==key)
            choices[kind] = choice
            if kind=='image': st.image(choice['value'], width=80 if compact else 320)
            else: st.caption(tables.preview(choice['value'],100)) if compact else st.text(choice['value'])
            st.caption(choice['source']+' · Purchases '+fmt(choice['metrics'].get('purchases'))+' · ROAS '+fmt(choice['metrics'].get('roas')))
            if choice.get('evidence_dates'):
                dates=choice['evidence_dates']
                st.caption(f"Asset reports cover {len(dates)} dates, {dates[0]} to {dates[-1]}. Last observed: {choice.get('last_observed') or 'unavailable'}.")
            own = [c for c in candidates if str(c['ad_id'])==str(selected['ad_id'])]
            if len(own)==1: complete[kind] = own[0]
            elif own:
                st.caption('Select the '+kind.replace('_',' ')+' reference from this multi-asset ad. The complete served combination is unconfirmed.')
                own_key=st.selectbox('Complete-ad '+kind.replace('_',' '),[c['key'] for c in own],format_func=lambda k, items=tuple(own):next((c['value'][:100] for c in items if c['key']==k),str(k)),key='review-own-'+kind+'-'+scope+'-'+selected['ad_id'])
                complete[kind]=next(c for c in own if c['key']==own_key)
    actor = str((st.session_state.get('sports_cave_current_user') or {}).get('id') or 'sports_cave_os')
    action_columns = st.columns(3) if compact else [st,st,st]
    if action_columns[0].button('Save winner selection'):
        try:
            store.save_selection({**context,'scope':scope,'overall':overall, **{k:v['key'] for k,v in choices.items()}},actor)
            _load_preferences.clear(context['account_id'])
            st.success('Internal winner selection saved to Supabase.')
        except Exception as error: st.error(sync_service.safe_error(error))
    st.caption('Refresh Winning Ad preserves this ad’s reference. Best Components creates an untested mix. Neither action publishes.')
    for index, (label, mode, values) in enumerate((('Refresh Winning Ad','complete_ad',complete),('Build From Best Components','best_components',choices))):
        if action_columns[index+1].button(label, disabled=len(values)!=3, type='primary' if mode=='complete_ad' else 'secondary'):
            try:
                mapping = next((m for m in history['mapping'] if str(m['ad_id'])==str(selected['ad_id'])), {})
                package = handoff.build_package(selected, values, {**context,'product_mapping':mapping}, mode)
                with st.spinner('Saving original winner reference…'): handoff.queue(package, st.session_state, actor)
                st.session_state['current_page'] = CREATIVE_REFRESH_ROUTE
                st.session_state['selected_page'] = CREATIVE_REFRESH_ROUTE
                st.session_state['current_page_source'] = 'meta-review-winner'
                st.query_params['page'] = CREATIVE_REFRESH_PAGE_KEY
                st.rerun()
            except Exception as error: st.error(sync_service.safe_error(error))


def simple_winner(ads,history,context):
    st.markdown('**SPORTS CAVE WINNER**')
    winner=analysis.choose_winner(ads)
    scope=hashlib.sha256(json.dumps(context,sort_keys=True,default=str).encode()).hexdigest()[:12]
    key='va-winner-'+str(context['campaign_id'])
    ids=[a['ad_id'] for a in ads]; by_id={a['ad_id']:a for a in ads}
    saved=next((r['context'].get('overall','Automatic') for r in history['selections'] if r['action_type']=='meta_review_selection' and r['context'].get('scope')==scope),'Automatic')
    options=['Automatic']+ids
    if st.session_state.get(key) not in options: st.session_state[key]=saved if saved in options else 'Automatic'
    chosen=st.selectbox('Winner to use',options,key=key,format_func=lambda value:
        ('Automatic Best Ad — '+str(winner.get('ad_name') or winner['ad_id']) if winner else 'Automatic Best Ad — Insufficient data') if value=='Automatic' else str(by_id[value].get('ad_name') or value))
    selected=winner if chosen=='Automatic' else by_id[chosen]
    complete={}
    if selected:
        st.caption('Selected Winner: '+str(selected.get('ad_name') or selected['ad_id']))
        for kind in ('image','primary_text','headline'):
            candidates=[c for c in analysis.component_candidates(ads,kind,history['assets']) if str(c['ad_id'])==str(selected['ad_id'])]
            if len(candidates)==1: complete[kind]=candidates[0]
            elif candidates:
                choice=st.selectbox('Choose original '+kind.replace('_',' '),[c['key'] for c in candidates],
                    format_func=lambda k,items=candidates:next(c['value'][:100] for c in items if c['key']==k),key=key+'-'+selected['ad_id']+'-'+kind)
                complete[kind]=next(c for c in candidates if c['key']==choice)
    else: st.caption('Insufficient data. Select an ad explicitly to use it as a reference.')
    actor=str((st.session_state.get('sports_cave_current_user') or {}).get('id') or 'sports_cave_os')
    reference_key=scope+'-'+hashlib.sha256(json.dumps({'chosen':chosen,'complete':complete},sort_keys=True,default=str).encode()).hexdigest()[:12]
    if st.button('APPLY TO CREATIVE REFRESH',type='primary',disabled=not selected or len(complete)!=3,key='va-apply-'+scope):
        try:
            b=selected.get('benchmark') or {}
            mapping=next((m for m in history['mapping'] if str(m['ad_id'])==str(selected['ad_id'])),{})
            package=handoff.build_package(selected,complete,{**context,'product_mapping':mapping,
                'market':b.get('country','UNKNOWN'),'format':b.get('format','UNKNOWN'),
                'recommendation_context':b,'last_sale':selected.get('recency',{})},'complete_ad')
            with st.spinner('Saving winning image and reference…'):
                st.session_state['va-handoff-link-'+reference_key]=handoff.queue_link(package,actor)
        except Exception as error: st.error(sync_service.safe_error(error))
    url=st.session_state.get('va-handoff-link-'+reference_key)
    if url:
        st.link_button('OPEN CREATIVE REFRESH',url,type='primary')
        st.caption('Opens a new tab with the saved winner. Meta Review stays open.')
    with st.expander('Advanced winner options',expanded=False):
        winner_board(ads,history,context,compact=False)


def live_status(entry, label):
    if entry['error']:
        st.error('LIVE META UNAVAILABLE · '+entry['error'])
    if entry.get('refreshed_at'):
        stamp = datetime.fromisoformat(entry['refreshed_at']).astimezone(ZoneInfo('Australia/Sydney'))
        source = 'STALE CACHED META' if entry['stale'] else 'LIVE META · brief cache'
        st.caption(f"{label} · {source} · Refreshed {stamp:%d %b %Y %I:%M:%S %p %Z}")


def dismiss_campaign():
    st.session_state['meta-review-table-epoch'] = st.session_state.get('meta-review-table-epoch',0)+1


@st.dialog('Campaign review', width='large', on_dismiss=dismiss_campaign)
def campaign_popup(config, campaign, since, until):
    render_campaign_details(config, campaign, since, until)


def render_campaign_details(config, campaign, since, until):
    cid=campaign['campaign_id']
    cache=st.session_state.setdefault('meta-review-live-cache',{})
    st.markdown('<h3 class="meta-review-modal-marker">'+escape(str(campaign.get('campaign_name') or cid))+'</h3>',unsafe_allow_html=True)
    stamp=tables.started(campaign)
    st.caption(f"{campaign.get('effective_status') or campaign.get('status') or 'Unknown'} · Started {stamp:%d %b %Y}" if stamp else (campaign.get('status') or 'Unknown'))
    with st.spinner('Reading selected campaign…'):
        entry=live.cached_read(cache,(live.scope(config),'campaign',cid,since,until),
            lambda:live.load_campaign(config,cid,since,until))
    live_status(entry,'Ads / available Meta history')
    if entry['data'] is None: return
    history=entry['data']
    history['currency']=(campaign.get('benchmark') or {}).get('currency','UNKNOWN')
    aid=config['ad_account_id'].removeprefix('act_')
    try:
        preferences=_load_preferences(aid)
        # Persistence may supply decisions/mapping only, never Graph performance.
        for key in ('selections','mapping'): history[key]=preferences.get(key,[])
    except Exception:
        st.warning('Saved Sports Cave selections/mapping are unavailable. Live Meta review remains available; saving a selection or handoff requires storage.')
    ads=build_ads(history,cid)
    if not ads:
        st.info('No readable ads returned for this campaign.')
        return
    formats={ad['benchmark']['format'] for ad in ads}
    format=next(iter(formats)) if len(formats)==1 else 'UNKNOWN'
    current=campaign.get('benchmark') or {}
    campaign['benchmark']=benchmarks.evaluate(campaign.get('metrics') or {},format,current.get('country','UNKNOWN'),current.get('currency','UNKNOWN'))
    sale_entry=live.cached_read(cache,(live.scope(config),'last-sale-ads',cid),
        lambda:recency.load(config,cid,'ad',campaign.get('account_timezone','Australia/Sydney')))
    for ad in ads: ad['recency']=recency.signal({**ad,'metrics':ad.get('benchmark_metrics',ad['metrics'])},sale_entry['data'])
    summary=tables.va_campaign_rows([campaign])[0]
    summary={k:summary[k] for k in ('Spend','Sales','ROAS','CPA','Last Sale','Action')}
    st.dataframe(tables.va_styled([summary],[campaign]),hide_index=True,placeholder='—',width='stretch',height=72,row_height=30)
    # Enrich only this brief live overview cache with already-read format evidence.
    for key,cached in cache.items():
        if key[:2]==(live.scope(config),'overview') and cached.get('data'):
            for item in cached['data'].get('campaigns',[]):
                if item['campaign_id']==cid: item['benchmark']=campaign['benchmark']
    st.caption('Select a creative row to view its full image, copy and reporting details.')
    event=st.dataframe(tables.va_styled(tables.va_ad_rows(ads),ads),hide_index=True,width='stretch',placeholder='—',
        height=min(390,40+64*len(ads)),row_height=64,on_select='rerun',selection_mode=['single-row','single-cell'],
        key='meta-review-creative-table-'+cid,
        column_config={**{k:st.column_config.Column(help=v) for k,v in tables.HELP.items()},'Creative':st.column_config.ImageColumn(width=76,pinned=True),
            'Ad':st.column_config.TextColumn(width=180,pinned=True),
            'Primary Text':st.column_config.TextColumn(width=210),
            'Headline':st.column_config.TextColumn(width=170),
            'Result':st.column_config.TextColumn(width=190)})
    selected=tables.selected_row(event,ads)
    if selected:
        selection_key='va-table-selected-'+cid
        if st.session_state.get(selection_key)!=selected['ad_id']:
            st.session_state['va-winner-'+cid]=selected['ad_id']
            st.session_state[selection_key]=selected['ad_id']
        with st.expander('View details · '+str(selected.get('ad_name') or selected['ad_id']),expanded=True):
            ad_card(selected)
    with st.container(key='meta-review-winner-controls'):
        winner_board(ads,history,{'account_id':aid,'campaign_id':cid,'campaign_name':campaign.get('campaign_name'),
            'market':'All','date_range':f'{since or "available"} — {until}'},compact=True)
    saved=[r for r in history['selections'] if r['action_type']=='meta_review_handoff' and str(r['context'].get('campaign_id'))==str(cid)]
    if saved:
        with st.expander('Saved winner handoffs'):
            chosen=st.selectbox('Saved reference',range(len(saved)),format_func=lambda i:f"{saved[i]['context'].get('ad_name')} · {saved[i].get('created_at')}")
            if st.button('Open saved winner in Creative Refresh'):
                st.session_state[handoff.PENDING]=saved[chosen]['context']
                st.session_state['current_page']=CREATIVE_REFRESH_ROUTE
                st.session_state['selected_page']=CREATIVE_REFRESH_ROUTE
                st.query_params['page']=CREATIVE_REFRESH_PAGE_KEY
                st.rerun()


def render_page():
    st.title('Meta Review')
    st.markdown("""<style>
    div[role="dialog"]:has(.meta-review-modal-marker) {
        width:min(96vw,1680px); max-width:96vw; max-height:92vh; overflow-y:auto;
    }
    </style>""",unsafe_allow_html=True)
    config=meta.get_meta_config()
    account_scope=live.scope(config)
    cache=st.session_state.setdefault('meta-review-live-cache',{})
    if st.session_state.get('meta-review-live-scope')!=account_scope:
        cache.clear()
        st.session_state['meta-review-live-scope']=account_scope
        dismiss_campaign()
    controls=st.columns([1,1,4],vertical_alignment='bottom')
    if controls[0].button('Refresh From Meta',disabled=not config.get('configured')):
        live.invalidate(cache,account_scope)
        dismiss_campaign()
    sort_by=controls[1].selectbox('Sort By',tables.SORT_OPTIONS)
    today=datetime.now(ZoneInfo('Australia/Sydney')).date()
    period=controls[2].date_input('Reporting period (Australia/Sydney)',
        value=(today-timedelta(days=1),today),max_value=today,format='DD/MM/YYYY')
    if len(period)!=2:
        st.info('Select both the start and end of the reporting period.')
        return
    since,until=period
    if not config.get('configured'):
        st.caption('Meta connection unavailable · Configure the existing account connection.')
        st.dataframe([],column_order=['Campaign','Status','Started']+[label for label,_ in tables.METRICS],hide_index=True,width='stretch',placeholder='—')
        return
    # Page-scoped only: metadata and one campaign-level Insights edge. Never startup/ad downloads.
    with st.spinner('Reading campaign overview…'):
        entry=live.cached_read(cache,(account_scope,'overview',since,until),
            lambda:live.load_overview(config,since,until))
    data=entry['data']
    account=(data or {}).get('account',{})
    refreshed=datetime.fromisoformat(entry['refreshed_at']).astimezone(ZoneInfo('Australia/Sydney')).strftime('%d %b %I:%M %p') if entry.get('refreshed_at') else 'not yet refreshed'
    source='STALE CACHED META' if entry['stale'] else 'LIVE META'
    st.markdown(f"**{source} · {since:%d %b %Y} – {until:%d %b %Y} · {account.get('currency') or 'Currency unavailable'}**")
    st.caption(f"{account.get('name') or 'Meta account'} · {'Unavailable' if entry['error'] else 'Connected'} · Last refreshed {refreshed} · Account attribution settings")
    if entry['error']: st.error('LIVE META UNAVAILABLE · '+entry['error'])
    if data is None: return
    if not data['campaigns']:
        st.info('No live campaigns returned.')
        return
    sale_entry=live.cached_read(cache,(account_scope,'last-sale-campaigns'),
        lambda:recency.load(config,config['ad_account_id'],'campaign',account.get('timezone_name') or 'Australia/Sydney'))
    for row in data['campaigns']:
        row['recency']=recency.signal(row,sale_entry['data'])
        row['account_timezone']=account.get('timezone_name') or 'Australia/Sydney'
    rows=tables.sort_campaigns(data['campaigns'],sort_by)
    if not rows:
        st.info('No live campaigns returned.')
        return
    st.caption('Select a campaign row to inspect its creatives and choose a winner.')
    key=f"meta-review-campaign-table-{sort_by}-{since}-{until}-{st.session_state.get('meta-review-table-epoch',0)}"
    event=st.dataframe(tables.va_styled(tables.va_campaign_rows(rows),rows),hide_index=True,width='stretch',placeholder='—',
        height=min(660,40+32*len(rows)),row_height=32,on_select='rerun',selection_mode=['single-row','single-cell'],key=key,
        column_config={'Campaign':st.column_config.TextColumn(width=280,pinned=True),
            **{label:st.column_config.NumberColumn(width=65) for label,_ in tables.VA_CAMPAIGN_METRICS},
            'Status':st.column_config.TextColumn(width=90),'Last Sale':st.column_config.TextColumn(width=155,help='Supplemental Meta conversion-hour report. Approximate hour ranges; unavailable when unsupported.'),
            'Action':st.column_config.TextColumn(width=150,help='Recommendation only. Never changes Meta status.')})
    with st.expander('Advanced metrics',expanded=False):
        advanced=[{'Campaign':r.get('campaign_name'),**{x['Metric']:x['Value'] for x in tables.advanced_rows(r.get('metrics') or {},campaign=True)}} for r in rows]
        st.dataframe(advanced,hide_index=True,placeholder='—',width='stretch')
    selected=tables.selected_row(event,rows)
    if selected:
        campaign_popup(config,selected,since,until)
