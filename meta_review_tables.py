"""Compact presentation helpers. No changes to Meta evidence or winner decisions."""
from datetime import datetime, timezone
import math
import pandas as pd
import meta_review_analysis as analysis

METRICS = [('Spend','spend'), ('Purchases','purchases'), ('Meta Purchase Value','purchase_value'),
           ('ROAS','roas'), ('CPA','cpa'), ('Link CTR','ctr'), ('CPC','cpc'),
           ('ATC','add_to_cart'), ('Checkout','checkout')]


def started(campaign):
    for key in ('start_time', 'created_time'):
        try:
            value = datetime.fromisoformat(str(campaign.get(key) or '').replace('Z','+00:00'))
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        except ValueError:
            pass
    return None


def sort_campaigns(campaigns, sort_by='Newest'):
    def key(row):
        stamp = started(row)
        newest = stamp.timestamp() if stamp else -math.inf
        if sort_by == 'Newest':
            return (newest, str(row['campaign_id']))
        metric = analysis.number((row.get('metrics') or {}).get('roas' if sort_by=='ROAS' else 'purchases'))
        return (metric is not None, metric if metric is not None else -math.inf, newest, str(row['campaign_id']))
    return sorted(campaigns, key=key, reverse=True)


def metrics_row(metrics):
    return {label: metrics.get(key) for label, key in METRICS}


def campaign_rows(campaigns):
    return [{'Campaign': r.get('campaign_name') or r['campaign_id'],
             'Status': r.get('effective_status') or r.get('status') or '—',
             'Started': started(r).strftime('%d %b %Y') if started(r) else '—',
             **metrics_row(r.get('metrics') or {})} for r in campaigns]


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
             **{label: ad['metrics'].get(key) for label,key in METRICS if label!='Meta Purchase Value'},
             'Result': labels[ad['ad_id']]} for ad in ads]


def styled(rows):
    """Numeric table sorting stays numeric; the UI supplies placeholder='—' for nulls."""
    frame=pd.DataFrame(rows)
    formats={label: ('${:,.2f}' if label in ('Spend','Meta Purchase Value','CPA','CPC') else
                    '{:,.0f}' if label in ('Purchases','ATC','Checkout') else
                    '{:.2f}%' if label=='Link CTR' else '{:.2f}')
             for label,_ in METRICS if label in frame.columns}
    result=frame.style.format(formats,na_rep='—')
    if 'Status' in frame:
        result=result.map(lambda value: 'background-color: #f1e9d5; color: #655020; font-weight: 600'
                          if value=='ACTIVE' else 'color: #777777',subset=['Status'])
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
