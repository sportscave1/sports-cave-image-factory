"""Compact presentation helpers. No changes to Meta evidence or winner decisions."""
from datetime import datetime, timezone
import math
import pandas as pd
import meta_review_analysis as analysis

METRICS = [('Spend','spend'), ('Purchases','purchases'), ('Meta Purchase Value','purchase_value'),
           ('ROAS','roas'), ('CPA','cpa'), ('CTR','click_ctr'), ('CPC','cpc'),
           ('Link CTR','ctr'), ('Link CPC','cost_per_link_click'), ('Out CTR','outbound_ctr'),
           ('Out CPC','outbound_cpc'), ('LPV','landing_page_views'), ('LPV %','lpv_rate'),
           ('Cost/LPV','cost_per_lpv'), ('ATC','add_to_cart'), ('ATC %','atc_rate'),
           ('Cost/ATC','cost_per_atc'), ('Checkout','checkout'), ('Checkout %','checkout_rate'),
           ('Cost/Checkout','cost_per_checkout'), ('Purchase CVR','purchase_cvr'),
           ('Checkout → Purchase','checkout_purchase'), ('Frequency','frequency'),
           ('CPM','cpm'), ('Impressions','impressions'), ('Reach','reach'),
           ('Clicks','clicks'),('Link clicks','inline_link_clicks'),('Outbound clicks','outbound_clicks')]
MONEY={'Spend','Meta Purchase Value','CPA','CPC','Link CPC','Out CPC','Cost/LPV','Cost/ATC','Cost/Checkout','CPM'}
PERCENT={'CTR','Link CTR','Out CTR','LPV %','ATC %','Checkout %','Purchase CVR','Checkout → Purchase'}
COUNTS={'Purchases','LPV','ATC','Checkout','Impressions','Reach','Clicks','Link clicks','Outbound clicks'}
SORT_METRICS = {
    'Best Score': ('score', False), 'ROAS': ('roas', False), 'Sales': ('purchases', False),
    'Spend': ('spend', False), 'CPA': ('cpa', True), 'CTR': ('click_ctr', False),
    'ATC': ('add_to_cart', False), 'Checkout': ('checkout', False),
    'Purchase Value': ('purchase_value', False), 'CPC': ('cpc', True),
    'Link CTR': ('ctr', False), 'Link CPC': ('cost_per_link_click', True),
    'Outbound CTR': ('outbound_ctr', False), 'Outbound CPC': ('outbound_cpc', True),
    'Landing Page Views': ('landing_page_views', False), 'LPV %': ('lpv_rate', False),
    'Cost / LPV': ('cost_per_lpv', True), 'ATC %': ('atc_rate', False),
    'Cost / ATC': ('cost_per_atc', True), 'Checkout %': ('checkout_rate', False),
    'Cost / Checkout': ('cost_per_checkout', True), 'Purchase CVR': ('purchase_cvr', False),
    'Checkout → Purchase': ('checkout_purchase', False), 'Frequency': ('frequency', True),
    'CPM': ('cpm', True), 'Impressions': ('impressions', False), 'Reach': ('reach', False),
    'Clicks': ('clicks', False), 'Link Clicks': ('inline_link_clicks', False),
    'Outbound Clicks': ('outbound_clicks', False),
}
SORT_OPTIONS = ['Newest', *list(SORT_METRICS)[:8], 'Last Sale', *list(SORT_METRICS)[8:]]
HELP={'LPV %':'Landing Page Views ÷ Link Clicks × 100', 'ATC %':'Add to Carts ÷ Landing Page Views × 100',
      'Checkout %':'Initiate Checkouts ÷ Landing Page Views × 100','Purchase CVR':'Purchases ÷ Landing Page Views × 100',
      'Cost/ATC':'Spend ÷ Add to Carts','Cost/Checkout':'Spend ÷ Initiate Checkouts',
      'Score':'Sports Cave historical benchmark score. No locked Sports Cave UK cost benchmark yet. UNKNOWN format excludes format-specific scoring.'}


def score_columns(row):
    b=row.get('benchmark') or {}
    return {'Format':b.get('format','UNKNOWN'),'Market':b.get('country','UNKNOWN'),
            'Score':b.get('score'),'Recommendation':b.get('recommendation','NO DATA')}


def started(campaign):
    for key in ('start_time', 'created_time'):
        try:
            value = datetime.fromisoformat(str(campaign.get(key) or '').replace('Z','+00:00'))
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        except ValueError:
            pass
    return None


def sort_campaigns(campaigns, sort_by='Newest'):
    # Retain helper aliases used by existing integrations; expose only SORT_OPTIONS.
    sort_by={'Purchases':'Sales','Highest Score':'Best Score','Highest Spend':'Spend','Highest ROAS':'ROAS'}.get(sort_by,sort_by)
    if sort_by not in (*SORT_OPTIONS,'Oldest','Lowest Score'):
        raise ValueError('Unknown campaign sort option.')
    def key(row):
        stamp = started(row)
        newest = stamp.timestamp() if stamp else -math.inf
        if sort_by in ('Newest','Oldest'):
            return ((-newest if sort_by=='Oldest' and stamp else newest), str(row['campaign_id']))
        if sort_by=='Last Sale':
            recency=row.get('recency') or {}
            # Only structured, validated evidence emitted by the recency helper.
            timestamp=recency.get('sale_sort_timestamp')
            group=3 if timestamp is not None else {'older':2,'no_sale':1}.get(recency.get('sale_sort_state'),0)
            return (group,timestamp if timestamp is not None else newest,newest,str(row['campaign_id']))
        field,ascending=('score',True) if sort_by=='Lowest Score' else SORT_METRICS[sort_by]
        metric=analysis.number((row.get('benchmark') or {}).get(field) if field=='score' else (row.get('metrics') or {}).get(field))
        if ascending and metric is not None: metric=-metric
        return (metric is not None, metric if metric is not None else -math.inf, newest, str(row['campaign_id']))
    return sorted(campaigns, key=key, reverse=True)


def metrics_row(metrics):
    return {label: metrics.get(key) for label, key in METRICS}


def campaign_rows(campaigns):
    return [{'Campaign': r.get('campaign_name') or r['campaign_id'],
             'Status': r.get('effective_status') or r.get('status') or '—',
             'Started': started(r).strftime('%d %b %Y') if started(r) else '—',
             **metrics_row(r.get('metrics') or {}), **score_columns(r)} for r in campaigns]


def preview(value, limit=140):
    text = ' '.join(str(value or '').split())
    return text if len(text)<=limit else text[:limit-1].rstrip()+'…'


def result_labels(ads):
    winner = analysis.choose_winner(ads)
    leaders = analysis.signal_leaders(ads)
    labels = {}
    names = {'WINNER — REFRESH THIS':'Winner','SCALE CANDIDATE':'Winner',
             'NEEDS MORE SPEND':'Needs more spend','INSUFFICIENT DATA':'Needs more data',
             'WATCH':'Watch','REFRESH CREATIVE':'Refresh','KILL CANDIDATE':'Kill candidate',
             'LANDING PAGE / PRODUCT ISSUE':'Review landing page'}
    for ad in ads:
        if ad['decision']['label'] in ('KILL CANDIDATE','REFRESH CREATIVE','LANDING PAGE / PRODUCT ISSUE'):
            label=names[ad['decision']['label']]
        elif winner and ad['ad_id']==winner['ad_id']:
            label='Winner'
        elif not winner and leaders['commercial'] and ad['ad_id']==leaders['commercial']['ad_id']:
            label='Strongest intent · low confidence'
        elif not winner and leaders['click'] and ad['ad_id']==leaders['click']['ad_id']:
            label='Strongest click signal · low confidence'
        else:
            label=names.get(ad['decision']['label'],ad['decision']['label'].title())
        labels[ad['ad_id']]=label
    return labels


def creative_rows(ads):
    labels=result_labels(ads)
    return [{'Creative': next(iter(ad['assets']['image']),{}).get('value'),
             'Ad': ad.get('ad_name') or ad['ad_id'],
             'Primary Text': preview(' / '.join(x['value'] for x in ad['assets']['primary_text'])),
             'Headline': ' / '.join(x['value'] for x in ad['assets']['headline']) or '—',
             **{label: ad.get('benchmark_metrics',ad['metrics']).get(key) for label,key in METRICS},
             **({'Result':labels[ad['ad_id']]} if not ad.get('benchmark') else {}), **score_columns(ad)} for ad in ads]


def styled(rows, evidence=None):
    """Numeric table sorting stays numeric; the UI supplies placeholder='—' for nulls."""
    frame=pd.DataFrame(rows)
    formats={label: ('${:,.2f}' if label in MONEY else
                    '{:,.0f}' if label in COUNTS else
                    '{:.2f}%' if label in PERCENT else '{:.2f}')
             for label,_ in METRICS if label in frame.columns}
    if 'Score' in frame: formats['Score']='{:.1f}'
    result=frame.style.format(formats,na_rep='—')
    if 'Status' in frame:
        result=result.map(lambda value: 'background-color: #f1e9d5; color: #655020; font-weight: 600'
                          if value=='ACTIVE' else 'color: #777777',subset=['Status'])
    if evidence:
        styles=pd.DataFrame('',index=frame.index,columns=frame.columns)
        palette={'GREEN':'color: #287044','AMBER':'color: #926600','RED':'color: #ae3434','NEUTRAL':'color: #777777'}
        for i,item in enumerate(evidence):
            b=item.get('benchmark') or {}
            for label,key in METRICS:
                if label in styles: styles.loc[i,label]=palette[b.get('cells',{}).get(key,{}).get('band','NEUTRAL')]
            if 'Score' in styles:
                score=b.get('score')
                band='NEUTRAL' if score is None or b.get('stage')=='LEARNING' else 'GREEN' if score>=7 else 'AMBER' if score>=4 else 'RED'
                styles.loc[i,'Score']=palette[band]+'; font-weight: 700'
            if 'Recommendation' in styles:
                rec=b.get('recommendation')
                band='GREEN' if rec in ('TOP WINNER','KEEP RUNNING') else 'RED' if rec in ('STOP / REPLACE','REFRESH CREATIVE') else 'NEUTRAL' if rec in ('NO DATA','LEARNING') else 'AMBER'
                styles.loc[i,'Recommendation']=palette[band]+'; font-weight: 600'
        result=result.apply(lambda _:styles,axis=None)
    return result


def selected_row(event, rows):
    """Selection indices map to the displayed order, never an unsorted source list."""
    selection = event.get('selection', {}) if isinstance(event, dict) else getattr(event, 'selection', {})
    indexes = selection.get('rows', [])
    cells=selection.get('cells', [])
    if len(cells)==1 and len(cells[0])==2:
        indexes=[cells[0][0]]
    if len(indexes)==1 and isinstance(indexes[0],int) and 0<=indexes[0]<len(rows):
        return rows[indexes[0]]
    return None


VA_METRICS=[('Spend','spend'),('Sales','purchases'),('ROAS','roas'),('CPA','cpa'),('CTR','click_ctr'),('ATC','add_to_cart'),('Checkout','checkout')]
MONEY.add('Spend')
COUNTS.add('Sales')


def va_campaign_rows(rows):
    return [{'Campaign':r.get('campaign_name') or r['campaign_id'],
             'Status':r.get('effective_status') or r.get('status') or '—',
             **{label:(r.get('metrics') or {}).get(key) for label,key in VA_METRICS},
             'Last Sale':r.get('recency',{}).get('text','Unavailable'),
             'Action':r.get('recency',{}).get('action',(r.get('benchmark') or {}).get('recommendation','NO DATA'))} for r in rows]


def va_ad_rows(rows):
    return [{'Creative':next(iter(r['assets']['image']),{}).get('value'),'Ad':r.get('ad_name') or r['ad_id'],
             **{label:r.get('benchmark_metrics',r['metrics']).get(key) for label,key in VA_METRICS if label!='Spend'},
             'Last Sale':r.get('recency',{}).get('text','Unavailable'),
             'Action':r.get('recency',{}).get('action',(r.get('benchmark') or {}).get('recommendation','NO DATA'))} for r in rows]


def va_styled(rows, evidence):
    frame=pd.DataFrame(rows)
    formats={label:'${:,.2f}' if label in MONEY else '{:,.0f}' if label in COUNTS else '{:.2f}%' if label in PERCENT else '{:.2f}'
             for label,key in VA_METRICS if label in frame}
    result=frame.style.format(formats,na_rep='—')
    styles=pd.DataFrame('',index=frame.index,columns=frame.columns)
    palette={'GREEN':'color: #287044','AMBER':'color: #926600','RED':'color: #ae3434','NEUTRAL':'color: #777777'}
    for i,row in enumerate(evidence):
        b=row.get('benchmark') or {}; rec=row.get('recency') or {}
        for label,key in [('ROAS','roas'),('CPA','cpa')]:
            if label in styles: styles.loc[i,label]=palette[b.get('cells',{}).get(key,{}).get('band','NEUTRAL')]
        if 'Last Sale' in styles: styles.loc[i,'Last Sale']=palette[rec.get('band','NEUTRAL')]
        action=rec.get('action',b.get('recommendation'))
        band='GREEN' if action in ('TOP WINNER','KEEP RUNNING') else 'RED' if action in ('STOP CAMPAIGN','STOP / REPLACE','REFRESH CREATIVE') else 'NEUTRAL' if action in ('LEARNING','NO DATA','PAUSED','ARCHIVED','HISTORICAL') else 'AMBER'
        if 'Action' in styles: styles.loc[i,'Action']=palette[band]+'; font-weight: 600'
    return result.apply(lambda _:styles,axis=None)


def advanced_rows(metrics):
    visible={key for _,key in VA_METRICS}
    return [{'Metric':label,'Value':metrics.get(key)} for label,key in METRICS if key not in visible]
