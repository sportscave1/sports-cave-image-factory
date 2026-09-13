"""Stored-history Meta decisions. Page open/import never calls Meta."""
from collections import defaultdict
from datetime import date, timedelta
import hashlib
import json
import streamlit as st
import meta_ads_client as meta
import meta_review_analysis as analysis
import meta_review_store as store
import meta_review_sync as sync_service
import meta_review_handoff as handoff
from ads_navigation import CREATIVE_REFRESH_PAGE_KEY, CREATIVE_REFRESH_ROUTE

aggregate_ad_metrics = analysis.aggregate_ad_metrics

def object_dict(value):
    return value if isinstance(value,dict) else {}

@st.cache_data(ttl=60, show_spinner=False)
def _load_review(account_id, since, until):
    return include_unavailable_objects(store.load_history(account_id, since, until))


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
        midpoint = len(valid)//2
        previous = analysis.aggregate([analysis.normalize_metrics(r) for r in valid[:midpoint]]) if midpoint >= 3 else None
        recent = analysis.aggregate([analysis.normalize_metrics(r) for r in valid[midpoint:]]) if previous else metrics
        ads.append({**row, 'assets': analysis.creative_assets(raw), 'metrics': metrics,
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
    labels = [('Spend','spend'),('Purchases','purchases'),('Meta purchase value','purchase_value'),
              ('Meta reported ROAS','roas'),('CPA','cpa'),('Link CTR','ctr')]
    cols = st.columns(3)
    for index, (label, key) in enumerate(labels):
        cols[index % 3].metric(label, fmt(metrics.get(key), '%' if key == 'ctr' else '×' if key == 'roas' else ''))
    if not compact:
        with st.expander('Funnel and more metrics'):
            labels = [('Add to cart','add_to_cart'),('Cost / ATC','cost_per_atc'),('Initiate checkout','checkout'),
                      ('Cost / checkout','cost_per_checkout'),('Link clicks','inline_link_clicks'),('CPC (all clicks)','cpc'),
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
            metrics_card(ad['metrics'])
        decision = ad['decision']
        message = f"{decision['label']} · {decision['confidence']} confidence — {decision['reason']}"
        if decision['tone'] == 'green': st.success(message)
        elif decision['tone'] == 'red': st.error(message)
        else: st.warning(message)


def winner_board(ads, history, context):
    winner = analysis.choose_winner(ads)
    st.subheader('Sports Cave winner')
    if winner:
        st.success('Automatic winning ad: '+str(winner.get('ad_name') or winner['ad_id']))
        st.write(winner['decision']['reason'])
    else:
        st.warning('INSUFFICIENT DATA for a trustworthy automatic winner. You can explicitly choose a reference below.')
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
    for kind, title in (('image','Winning image'),('primary_text','Winning primary text'),('headline','Winning headline')):
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
        if kind=='image': st.image(choice['value'], width=320)
        else: st.text(choice['value'])
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
    if st.button('Save winner selection'):
        try:
            store.save_selection({**context,'scope':scope,'overall':overall, **{k:v['key'] for k,v in choices.items()}},actor)
            _load_review.clear()
            st.success('Internal winner selection saved to Supabase.')
        except Exception as error: st.error(sync_service.safe_error(error))
    st.caption('Refresh Winning Ad preserves this ad’s reference. Best Components creates an untested mix. Neither action publishes.')
    for label, mode, values in (('Refresh Winning Ad','complete_ad',complete),('Build From Best Components','best_components',choices)):
        if st.button(label, disabled=len(values)!=3, type='primary' if mode=='complete_ad' else 'secondary'):
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


def render_page():
    st.title('Meta Review')
    st.caption('Stored Meta reporting → creative decisions → Creative Refresh. Live advertising is read-only.')
    config = meta.get_meta_config()  # Environment only; no request.
    aid = config.get('ad_account_id','').removeprefix('act_')
    if not aid:
        st.info('Set META_AD_ACCOUNT_ID to select reporting history. A token is only needed for sync.')
        return
    cols = st.columns(3)
    ranges = ['Last 7 days','Last 14 days','Last 30 days','Last 90 days','Lifetime / available history','Custom']
    selected_range = cols[0].selectbox('Date range', ranges, index=2)
    until = date.today()
    since = None if selected_range.startswith('Lifetime') else until-timedelta(days=int(selected_range.split()[1])-1) if selected_range != 'Custom' else until-timedelta(days=29)
    if selected_range=='Custom':
        since = cols[0].date_input('From', since)
        until = cols[0].date_input('Through', until)
        if since > until:
            st.error('Start date must precede end date.')
            return
    query = cols[1].text_input('Campaign search')
    status = cols[2].selectbox('Status',['All','ACTIVE','PAUSED','ARCHIVED','DELETED','COMPLETED'])
    with st.expander('Sync options and decision thresholds'):
        asset_sync = st.checkbox('Request Meta asset breakdowns',value=True)
        st.caption('Lifetime requests available Meta history; large accounts may need smaller ranges. Target markets reflect ad-set targeting, not country-attributed revenue.')
        st.dataframe([{'Threshold':k.replace('_',' ').title(),'Value':v} for k,v in analysis.Rules.from_env().__dict__.items()],hide_index=True)
        st.caption('META_REVIEW_* environment settings configure evidence thresholds. Confidence is not a statistical probability. No profit target is assumed when CPA/ROAS targets are unset.')
    if st.button('Sync Meta', disabled=not config['configured']):
        with st.status('Syncing Meta reporting…', expanded=True) as progress:
            try:
                result = sync_service.sync(since,until,lifetime=since is None,assets=asset_sync,progress=progress.write)
                _load_review.clear()
                progress.update(label='Reporting saved to Supabase',state='complete')
                for warning in result['warnings']: st.warning(warning)
            except Exception as error:
                progress.update(label='Sync failed — previous history retained',state='error')
                st.error(sync_service.safe_error(error))
    try: history = _load_review(aid,since,until)
    except Exception as error:
        st.error(sync_service.safe_error(error))
        st.caption('Install existing Ads Intelligence migrations and the Meta Review reporting migration before using this page.')
        return
    logs = history['logs']
    success = next((r for r in logs if r['status']=='success'), None)
    st.caption('Supabase history · Last successful Meta Review sync: '+str(success.get('finished_at') if success else 'Not yet synced'))
    if success and (success.get('context') or {}).get('warnings'):
        with st.expander('Stored sync capability notes'):
            for warning in success['context']['warnings']: st.warning(warning)
    if logs and logs[0]['status']=='error': st.warning(logs[0].get('error_message') or 'Last sync failed; showing stored history.')
    if logs and logs[0]['status']=='started': st.warning('The latest sync has no completion record (running or interrupted). Showing only committed reporting history.')
    campaigns = [r for r in history['campaigns'] if query.casefold() in str(r.get('campaign_name') or '').casefold() and (status=='All' or status in (r.get('status'),r.get('effective_status')) or (status=='COMPLETED' and (r.get('raw') or {}).get('_review_completed')))]
    if not campaigns:
        st.info('No stored campaigns match. Use Sync Meta to retrieve accessible current and historical campaigns.')
        return
    account = next(iter(history['accounts']), {})
    st.caption(f"{account.get('name') or aid} · Currency {account.get('currency') or 'unavailable'} · {since or 'Available stored history'} to {until}")
    summaries=[]
    campaign_ads=defaultdict(list)
    for ad in build_ads(history): campaign_ads[str(ad.get('campaign_id'))].append(ad)
    for campaign in campaigns:
        metrics=analysis.aggregate([a['metrics'] for a in campaign_ads[str(campaign['campaign_id'])]])
        summaries.append({'Campaign':campaign.get('campaign_name'),'Status':campaign.get('effective_status') or campaign.get('status'),
            **{label:fmt(metrics.get(key)) for label,key in [('Spend','spend'),('Purchases','purchases'),('Meta purchase value','purchase_value'),('ROAS','roas'),('CPA','cpa'),('Link CTR','ctr'),('CPC','cpc'),('ATC','add_to_cart'),('Checkout','checkout')]}})
    st.dataframe(summaries,hide_index=True,use_container_width=True)
    ids=[r['campaign_id'] for r in campaigns]
    cid=st.selectbox('Open campaign',ids,format_func=lambda key:next(r.get('campaign_name') or key for r in campaigns if r['campaign_id']==key))
    saved_handoffs=[r for r in history['selections'] if r['action_type']=='meta_review_handoff' and str(r['context'].get('campaign_id'))==str(cid)]
    if saved_handoffs:
        with st.expander('Saved winner handoffs'):
            chosen=st.selectbox('Saved reference',range(len(saved_handoffs)),format_func=lambda i:f"{saved_handoffs[i]['context'].get('ad_name')} · {saved_handoffs[i]['context'].get('mode')} · {saved_handoffs[i].get('created_at')}")
            if st.button('Open saved winner in Creative Refresh'):
                st.session_state[handoff.PENDING]=saved_handoffs[chosen]['context']
                st.session_state['current_page']=CREATIVE_REFRESH_ROUTE
                st.session_state['selected_page']=CREATIVE_REFRESH_ROUTE
                st.query_params['page']=CREATIVE_REFRESH_PAGE_KEY
                st.rerun()
    all_ads=campaign_ads[str(cid)]
    markets=sorted({country for a in all_ads for country in a['markets']})
    market=st.selectbox('Target market / country',['All']+markets)
    ads=[ad for ad in all_ads if market=='All' or market in ad['markets']]
    if not ads:
        st.info('No stored ads for this campaign and market.')
        return
    if market!='All':
        peers=[ad['metrics'] for ad in ads]
        for ad in ads:
            ad['decision']=analysis.analyse(ad['metrics'],peers)
            fatigue=analysis.analyse(ad['recent'],peers,ad['previous'])
            if fatigue['label']=='REFRESH CREATIVE': ad['decision']=fatigue
    metrics_card(analysis.aggregate([a['metrics'] for a in ads]),compact=True)
    st.caption('Creative snapshots show assets observed at sync, not reconstructed historical serving combinations. Expired image URLs need a new explicit sync.')
    page=st.number_input('Creative page (12 ads per page)',min_value=1,max_value=max(1,(len(ads)+11)//12),value=1,step=1,key='review-page-'+cid)
    for ad in ads[(page-1)*12:page*12]: ad_card(ad)
    observations=[r for r in history.get('observations',[]) if str(r['ad_id']) in {str(a['ad_id']) for a in ads}]
    if observations:
        with st.expander('Previously observed creative versions'):
            index=st.selectbox('Observed version',range(len(observations)),format_func=lambda i:f"Ad {observations[i]['ad_id']} · {observations[i]['observed_at']}")
            observed=observations[index]
            original=next(a for a in ads if str(a['ad_id'])==str(observed['ad_id']))
            # No performance is assigned to a historical revision without Meta evidence.
            ad_card({**original,'assets':analysis.creative_assets(observed['raw']),'metrics':analysis.aggregate([]),
                     'decision':{'label':'CREATIVE OBSERVATION','confidence':'Low','tone':'amber','reason':'Exact assets observed at this sync time; performance is not attributed to this revision.'}})
    winner_board(ads,history,{'account_id':aid,'campaign_id':cid,'campaign_name':next(c['campaign_name'] for c in campaigns if c['campaign_id']==cid),
                            'market':market,'date_range':f'{since or "available"} — {until}'})
