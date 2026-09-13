"""Locked Sports Cave 2026 benchmarks. Pure Graph-only decision support.

Rates use (amber entry, green entry); costs use (green maximum, amber maximum).
Continuous values between printed hundredths remain amber until the green entry.
Sales scores equally weight available purchase benchmarks; diagnostic weights are
the supplied relative weights. Currency thresholds are AUD, never FX-converted.
"""
from urllib.parse import urlparse
from meta_review_analysis import number, ratio

RATES = {
 'INSTANT EXPERIENCE': dict(click_ctr=(5.03,5.67),ctr=(2.35,2.99),outbound_ctr=(1.55,1.93),lpv_rate=(62,66),atc_rate=(2.6,5.7),checkout_rate=(.63,3.40)),
 'CAROUSEL': dict(click_ctr=(2.51,2.98),lpv_rate=(83,89),atc_rate=(.5,5.7),checkout_rate=(.5,1.90)),
}
COSTS = {
 ('AU','INSTANT EXPERIENCE'): dict(cpc=(.22,.25),cost_per_link_click=(.41,.63),outbound_cpc=(.64,1.45),cost_per_lpv=(.71,1.34),cost_per_checkout=(13.44,21.07)),
 ('AU','CAROUSEL'): dict(cpc=(.35,.48),cost_per_link_click=(.81,.98),outbound_cpc=(.83,1.08),cost_per_lpv=(.84,1.12),cost_per_atc=(16.91,45.82),cost_per_checkout=(26.57,48.63)),
 ('US','INSTANT EXPERIENCE'): dict(cpc=(.37,.57),cost_per_link_click=(.64,1.08),outbound_cpc=(.96,1.66),cost_per_lpv=(.97,1.70),cost_per_atc=(12.25,18.90),cost_per_checkout=(20.23,44.35)),
 ('US','CAROUSEL'): dict(cpc=(1.22,1.45),cost_per_link_click=(1.55,2.58),outbound_cpc=(1.68,2.70),cost_per_lpv=(1.79,2.85)),
}
WEIGHTS = {
 'INSTANT EXPERIENCE': dict(checkout_rate=20,atc_rate=10,cost_per_lpv=9,cost_per_checkout=7,outbound_cpc=9,cost_per_link_click=8,cpc=7,lpv_rate=5,click_ctr=5,cost_per_atc=8,ctr=5,outbound_ctr=4),
 'CAROUSEL': dict(checkout_rate=20,atc_rate=12,cost_per_lpv=11,cost_per_checkout=11,outbound_cpc=9,cost_per_link_click=9,cpc=8,lpv_rate=9,click_ctr=5),
}
PURCHASE_RATES = dict(purchase_cvr=(1.62,3.50),roas=(3.79,10.34),checkout_purchase=(45.1,75.7))
CPA = (28.24,62.65)
LEARNING, MATURE, DECISION = 28.24,41.58,62.65
COUNTRIES = {'AU':'Australia','US':'United States','GB':'United Kingdom'}


def action(row, source, name, default=None):
    entries=row.get(source)
    if not isinstance(entries,list): return default
    return next((number(x.get('value')) for x in entries if isinstance(x,dict) and x.get('action_type')==name),default)


def graph_metrics(row):
    """One aggregate Graph row. Canonical actions only, no alias fallbacks/sums."""
    row=row if isinstance(row,dict) else {}
    has_data=any(number(row.get(k)) is not None for k in ('spend','impressions','reach','clicks'))
    m={k:number(row.get(k)) for k in ('spend','impressions','reach','frequency','clicks','inline_link_clicks','cpc','cpm')}
    m.update(click_ctr=number(row.get('ctr')),ctr=number(row.get('inline_link_click_ctr')),
             cost_per_link_click=number(row.get('cost_per_inline_link_click')))
    for key,name in [('landing_page_views','landing_page_view'),('add_to_cart','add_to_cart'),('checkout','initiate_checkout'),('purchases','purchase')]:
        m[key]=action(row,'actions',name,0.0 if has_data else None)
    m['purchase_value']=action(row,'action_values','purchase',0.0 if has_data and m['purchases']==0 else None)
    m['roas']=action(row,'purchase_roas','omni_purchase')
    if m['roas'] is None: m['roas']=action(row,'purchase_roas','purchase')
    m['reported_roas']=m['roas']
    for key,source in [('outbound_clicks','outbound_clicks'),('outbound_ctr','outbound_clicks_ctr'),('outbound_cpc','cost_per_outbound_click')]:
        m[key]=action(row,source,'outbound_click')
    for key,n,d in [('lpv_rate','landing_page_views','inline_link_clicks'),('atc_rate','add_to_cart','landing_page_views'),('checkout_rate','checkout','landing_page_views'),('purchase_cvr','purchases','landing_page_views'),('checkout_purchase','purchases','checkout')]:
        m[key]=ratio(m[n],m[d],100)
    for key,d in [('cost_per_lpv','landing_page_views'),('cost_per_atc','add_to_cart'),('cost_per_checkout','checkout'),('cpa','purchases')]:
        m[key]=ratio(m['spend'],m[d])
    m['has_data']=has_data
    return m


def ad_format(creative):
    """IE destination metadata takes precedence over an embedded carousel."""
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('canvas_id','instant_experience_id') and item: yield True
                if key in ('link','url','website_url') and isinstance(item,str):
                    parsed=urlparse(item)
                    host=(parsed.hostname or '').lower()
                    if (host=='facebook.com' or host.endswith('.facebook.com')) and parsed.path.startswith(('/canvas/','/instant_experience/')): yield True
                yield from walk(item)
        elif isinstance(value,list):
            for item in value: yield from walk(item)
    creative=creative if isinstance(creative,dict) else {}
    if any(walk(creative)): return 'INSTANT EXPERIENCE'
    spec=creative.get('object_story_spec') or {}
    spec=spec if isinstance(spec,dict) else {}
    link=spec.get('link_data') or {}
    link=link if isinstance(link,dict) else {}
    if isinstance(link.get('child_attachments'),list) and len(link['child_attachments'])>1: return 'CAROUSEL'
    feed=creative.get('asset_feed_spec') or {}
    feed=feed if isinstance(feed,dict) else {}
    if 'CAROUSEL' in (feed.get('ad_formats') or []): return 'CAROUSEL'
    return 'UNKNOWN'


def market(rows):
    """Conservative rule: ANY positive spend in >1 country is MIXED."""
    countries={str(r.get('country') or 'UNKNOWN').upper() for r in rows if (number(r.get('spend')) or 0)>0}
    return next(iter(countries)) if len(countries)==1 else 'MIXED' if countries else 'UNKNOWN'


def maturity(m):
    spend=m.get('spend')
    if not m.get('has_data') or spend is None: return 'NO DATA'
    if (m.get('purchases') or 0)>0: return 'PURCHASES'
    return 'LEARNING' if spend<LEARNING else 'EARLY REVIEW' if spend<MATURE else 'MATURE REVIEW' if spend<=DECISION else 'DECISION POINT'


def metric_score(value, bounds, lower=False):
    value=number(value)
    if value is None: return (None,'NEUTRAL')
    a,b=bounds
    if lower:
        if value<=a: return (min(9,7+2*(a-value)/a),'GREEN')
        if value<=b: return (6-2*(value-a)/(b-a),'AMBER')
        return (max(1,3-2*(value-b)/b),'RED')
    if value<a: return (1+2*value/a,'RED')
    if value<b: return (4+2*(value-a)/(b-a),'AMBER')
    return (min(9,7+2*(value-b)/b),'GREEN')


def evaluate(m, format='UNKNOWN', country='UNKNOWN', currency='AUD'):
    stage=maturity(m)
    bounds={k:(v,False) for k,v in RATES.get(format,{}).items()}
    monetary=currency=='AUD' and country in ('AU','US')
    if monetary: bounds.update({k:(v,True) for k,v in COSTS.get((country,format),{}).items()})
    sales=(m.get('purchases') or 0)>0
    if sales:
        bounds.update({k:(v,False) for k,v in PURCHASE_RATES.items()})
        if monetary: bounds['cpa']=(CPA,True)
    weights={k:1 for k in (*PURCHASE_RATES,'cpa')} if sales else WEIGHTS.get(format,{})
    cells={}
    for key,(thresholds,lower) in bounds.items():
        value=m.get(key)
        if stage=='LEARNING' and key in ('atc_rate','checkout_rate','lpv_rate') and value==0: continue
        score,band=metric_score(value,thresholds,lower)
        cells[key]={'score':score,'band':band,'weight':weights.get(key,0)}
    active={k:v for k,v in cells.items() if v['score'] is not None and v['weight']>0}
    total=sum(v['weight'] for v in active.values())
    score=sum(v['score']*v['weight'] for v in active.values())/total if total else None
    # Mature zero-event evidence must not be outweighed by cheap clicks. No fake
    # infinite costs or invented rate denominators: an explicit decision cap.
    low_intent=(not sales and stage in ('MATURE REVIEW','DECISION POINT') and format in RATES
                and m.get('add_to_cart')==0 and m.get('checkout')==0)
    if low_intent and score is not None: score=min(score,3.9)
    recommendation='WATCH'
    if stage=='NO DATA': recommendation='NO DATA'
    elif sales:
        roas=m.get('roas')
        if roas is not None and roas>=10.34 and monetary and m.get('cpa') is not None and m['cpa']<=28.24: recommendation='TOP WINNER'
        elif roas is not None and roas>=3.79: recommendation='KEEP RUNNING'
        elif roas is not None: recommendation='WATCH PROFITABILITY'
    elif stage=='LEARNING': recommendation='LEARNING'
    elif (m.get('spend') or 0)>=MATURE and all(cells.get(k,{}).get('band')=='GREEN' for k in ('atc_rate','checkout_rate')): recommendation='CHECK STORE / CHECKOUT'
    elif score is not None and score<4 and stage=='DECISION POINT': recommendation='STOP / REPLACE'
    elif score is not None and score<4 and stage=='MATURE REVIEW': recommendation='REFRESH CREATIVE'
    elif score is not None and score>=7: recommendation='KEEP RUNNING'
    return dict(score=score,recommendation=recommendation,stage=stage,cells=cells,format=format,country=country,
                active_weight=total,low_intent=low_intent,currency=currency)
