"""Pure, deterministic Meta reporting. Unknown is never silently turned into zero."""
from collections import defaultdict
from dataclasses import dataclass
import math
import os
from urllib.parse import urlparse


ACTION_ALIASES = {
    'purchases': ('omni_purchase', 'purchase', 'offsite_conversion.fb_pixel_purchase', 'onsite_web_purchase'),
    'purchase_value': ('omni_purchase', 'purchase', 'offsite_conversion.fb_pixel_purchase', 'onsite_web_purchase'),
    'add_to_cart': ('omni_add_to_cart', 'add_to_cart', 'offsite_conversion.fb_pixel_add_to_cart'),
    'checkout': ('omni_initiated_checkout', 'initiate_checkout', 'offsite_conversion.fb_pixel_initiate_checkout'),
    'view_content': ('omni_view_content', 'view_content', 'offsite_conversion.fb_pixel_view_content'),
    'engagement': ('post_engagement',), 'reactions': ('post_reaction', 'like'),
    'comments': ('comment',), 'shares': ('post',), 'saves': ('onsite_conversion.post_save',),
    'video_views': ('video_view',), 'outbound_clicks': ('outbound_click',),
}
BASE_FIELDS = ('spend', 'impressions', 'clicks', 'inline_link_clicks',
               'instant_experience_clicks_to_open', 'instant_experience_clicks_to_start',
               'instant_experience_outbound_clicks')


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def action(row, key, source='actions'):
    """Pick ONE reporting scope; omni/pixel aliases overlap and must not be added."""
    entries = row.get(source)
    if not isinstance(entries, list):
        return None
    values = {item.get('action_type'): number(item.get('value')) for item in entries if isinstance(item, dict)}
    return next((values[name] for name in ACTION_ALIASES[key] if values.get(name) is not None), None)


def ratio(numerator, denominator, factor=1):
    return numerator / denominator * factor if numerator is not None and denominator else None


def normalize_metrics(row):
    row = row if isinstance(row, dict) else {}
    out = {key: number(row.get(key)) for key in BASE_FIELDS}
    for key in ACTION_ALIASES:
        source = 'action_values' if key == 'purchase_value' else 'outbound_clicks' if key == 'outbound_clicks' else 'actions'
        out[key] = action(row, key, source)
    # Reported ROAS is usable if value is absent, but never manufacture purchase value.
    out['reported_roas'] = action(row, 'purchases', 'purchase_roas')
    out['reach'] = number(row.get('reach'))
    out['frequency'] = number(row.get('frequency'))
    return derive(out)


def derive(out):
    out = dict(out)
    for key, count in (('cpa', 'purchases'), ('cost_per_atc', 'add_to_cart'),
                       ('cost_per_checkout', 'checkout'), ('cpc', 'clicks'), ('cost_per_link_click', 'inline_link_clicks')):
        out[key] = ratio(out.get('spend'), out.get(count))
    out['ctr'] = ratio(out.get('inline_link_clicks'), out.get('impressions'), 100)
    out['click_ctr'] = ratio(out.get('clicks'), out.get('impressions'), 100)
    out['cpm'] = ratio(out.get('spend'), out.get('impressions'), 1000)
    out['roas'] = ratio(out.get('purchase_value'), out.get('spend'))
    if out['roas'] is None:
        out['roas'] = out.get('reported_roas')
    return out


def aggregate(rows):
    rows = list(rows)
    fields = (*BASE_FIELDS, *ACTION_ALIASES)
    out = {key: sum(r[key] for r in rows) if rows and all(r.get(key) is not None for r in rows) else None for key in fields}
    out['reported_roas'] = (sum(r['reported_roas'] * r['spend'] for r in rows) / sum(r['spend'] for r in rows)
        if rows and all(r.get('reported_roas') is not None and r.get('spend') is not None for r in rows)
        and sum(r['spend'] for r in rows) else None)
    # Reach cannot be summed across dates or ads; frequency cannot be averaged as range frequency.
    out['reach'] = rows[0].get('reach') if len(rows) == 1 else None
    out['frequency'] = rows[0].get('frequency') if len(rows) == 1 else None
    frequencies = [r['frequency'] for r in rows if r.get('frequency') is not None]
    out['max_daily_frequency'] = max(frequencies) if frequencies else None
    return derive(out)


def aggregate_ad_metrics(rows):
    groups = defaultdict(list)
    for row in rows:
        if row.get('ad_id'):
            groups[str(row['ad_id'])].append(normalize_metrics(row))
    return {key: aggregate(values) for key, values in groups.items()}


def creative_assets(raw):
    """Preserve verbatim copy and every carousel/dynamic candidate. No generated assets."""
    raw = raw if isinstance(raw, dict) else {}
    spec = raw.get('object_story_spec') or {}
    feed = raw.get('asset_feed_spec') or {}
    spec = spec if isinstance(spec, dict) else {}
    feed = feed if isinstance(feed, dict) else {}
    link = spec.get('link_data') or spec.get('video_data') or spec.get('photo_data') or spec.get('template_data') or {}
    link = link if isinstance(link, dict) else {}
    result = {key: [] for key in ('image', 'primary_text', 'headline', 'description', 'cta', 'url')}
    def add(kind, value, identity='', **extra):
        if kind=='image':
            try:
                parsed=urlparse(value) if isinstance(value,str) else None
                if parsed is None or parsed.scheme!='https' or not parsed.hostname: return
            except ValueError:
                return
        if isinstance(value, str) and value.strip() and not any(x['value'] == value or (identity and x['id']==str(identity)) for x in result[kind]):
            result[kind].append({'value': value, 'id': str(identity or value), **extra})
    add('primary_text', link.get('message') or raw.get('body') or raw.get('primary_text'))
    add('headline', link.get('name') or link.get('title') or raw.get('title') or raw.get('headline'))
    add('description', link.get('description') or raw.get('description'))
    cta = link.get('call_to_action') or {}
    add('cta', cta.get('type') if isinstance(cta, dict) else cta)
    add('cta', raw.get('call_to_action_type'))
    cta_value = cta.get('value') if isinstance(cta, dict) else {}
    add('url', link.get('link') or raw.get('link_url') or (cta_value.get('link') if isinstance(cta_value, dict) else None))
    add('image', link.get('picture') or link.get('image_url') or raw.get('image_url'), link.get('image_hash') or raw.get('image_hash'))
    for kind, field in (('primary_text', 'bodies'), ('headline', 'titles'), ('description', 'descriptions')):
        for item in feed.get(field) or []:
            if isinstance(item, dict):
                add(kind, item.get('text'), item.get('id'))
    for item in feed.get('images') or []:
        if isinstance(item, dict):
            add('image', item.get('url'), item.get('hash'))
    for item in feed.get('videos') or []:
        if isinstance(item, dict):
            add('image', item.get('thumbnail_url'), item.get('video_id'), video=True)
    for item in link.get('child_attachments') or []:
        if isinstance(item, dict):
            add('image', item.get('picture'), item.get('image_hash'), carousel=True)
            add('headline', item.get('name'))
            add('description', item.get('description'))
            add('url', item.get('link'))
    for item in feed.get('call_to_action_types') if isinstance(feed.get('call_to_action_types'),list) else []:
        add('cta', item)
    for item in feed.get('link_urls') or []:
        if isinstance(item, dict):
            add('url', item.get('website_url'))
    if not result['image']:
        add('image', raw.get('thumbnail_url'), raw.get('image_hash') or raw.get('video_id'), thumbnail=True)
    result['dynamic'] = bool(feed)
    result['carousel'] = bool(link.get('child_attachments'))
    result['creative_id'] = str(raw.get('id') or '')
    return result


@dataclass(frozen=True)
class Rules:
    min_purchases: float = 3
    high_purchases: float = 10
    min_spend: float = 0  # zero means unset; no universal Sports Cave dollar economics
    target_cpa: float = 0
    target_roas: float = 0
    poor_spend_multiple: float = 3
    fatigue_frequency: float = 3
    fatigue_change: float = .25
    min_clicks: float = 50

    @classmethod
    def from_env(cls):
        return cls(**{key: number(os.getenv('META_REVIEW_' + key.upper()))
                      if number(os.getenv('META_REVIEW_' + key.upper())) is not None else value.default
                      for key, value in cls.__dataclass_fields__.items()})


def analyse(metrics, peers=(), previous=None, rules=None):
    r = rules or Rules.from_env()
    m = metrics
    spend, purchases = m.get('spend'), m.get('purchases')
    sufficient = bool(spend and purchases is not None and purchases >= max(r.min_purchases, 1) and spend >= r.min_spend)
    confidence = 'High' if sufficient and purchases >= max(r.high_purchases, r.min_purchases) else 'Medium' if sufficient else 'Low'
    result = {'label': 'INSUFFICIENT DATA', 'confidence': confidence, 'tone': 'amber',
              'reason': 'Missing delivery or purchase evidence. No trustworthy winner can be established.'}
    if spend is None or not spend or purchases is None:
        return result
    result.update(label='WATCH', reason='Commercial signals are inconclusive. Compare within this campaign and date range.')
    if not sufficient and (purchases > 0 or (m.get('checkout') or 0) > 0 or (m.get('add_to_cart') or 0) > 0):
        result.update(label='NEEDS MORE SPEND', reason=f'Early commercial signal, but only {purchases:g} reported purchases. Evidence threshold is {r.min_purchases:g}; this is not an established winner.')
    if r.target_cpa and spend >= r.target_cpa * r.poor_spend_multiple and purchases == 0:
        result.update(label='KILL CANDIDATE', tone='red', reason='Spend exceeds the configured test allowance with zero reported purchases. Read-only recommendation; investigate before stopping anything.')
    if m.get('inline_link_clicks', 0) is not None and (m.get('inline_link_clicks') or 0) >= r.min_clicks and m.get('add_to_cart') == 0:
        result.update(label='LANDING PAGE / PRODUCT ISSUE', tone='orange', reason='Meaningful link-click volume but zero reported add-to-carts. Investigate tracking, message match and product page; this is not proof of causation.')
    comparable = [p for p in peers if (p.get('purchases') or 0) >= max(r.min_purchases, 1) and p.get('roas') is not None and p.get('cpa') is not None]
    strong = sufficient and m.get('roas') is not None and m.get('cpa') is not None
    if r.target_roas:
        strong = strong and m['roas'] >= r.target_roas
    elif len(comparable) > 1:
        strong = strong and m['roas'] >= sorted(p['roas'] for p in comparable)[len(comparable)//2] and m['cpa'] <= sorted(p['cpa'] for p in comparable)[len(comparable)//2]
    else:
        strong = False
    if r.target_cpa:
        strong = strong and m['cpa'] <= r.target_cpa
    if strong:
        result.update(label='SCALE CANDIDATE' if confidence == 'High' and r.target_cpa and r.target_roas else 'WINNER — REFRESH THIS', tone='green',
                      reason=f'{purchases:g} reported purchases at sufficient spend; ROAS {m["roas"]:.2f} and CPA {m["cpa"]:.2f} meet configured targets or campaign comparison. Ad-level evidence, not causal asset attribution.')
        supporting=[]
        for key,label in (('ctr','link CTR'),('cpc','CPC'),('checkout','checkouts'),('add_to_cart','add-to-carts')):
            if m.get(key) is not None: supporting.append(f'{label} {m[key]:.2f}')
        if supporting: result['reason']+=' Supporting signals: '+', '.join(supporting)+'.'
        if m.get('engagement') is not None: result['reason']+=' Engagement is context only; it did not determine the winner.'
    if previous and (previous.get('purchases') or 0) >= r.min_purchases:
        falling = previous.get('ctr') and m.get('ctr') is not None and m['ctr'] <= previous['ctr'] * (1-r.fatigue_change)
        worsening = previous.get('cpa') and m.get('cpa') is not None and m['cpa'] >= previous['cpa'] * (1+r.fatigue_change)
        frequency = m.get('max_daily_frequency') or m.get('frequency') or 0
        if (falling or worsening) and frequency >= r.fatigue_frequency:
            result.update(label='REFRESH CREATIVE', tone='amber', reason='Earlier purchases were meaningful; recent CTR fell or CPA worsened alongside high daily frequency. Possible fatigue; audience and offer changes can also explain it.')
    return result


def choose_winner(ads, rules=None):
    eligible = [a for a in ads if a.get('decision', {}).get('label') in ('WINNER — REFRESH THIS', 'SCALE CANDIDATE')]
    return next(iter(sorted(eligible, key=lambda a: (-(a['metrics'].get('purchases') or 0),
        -(a['metrics'].get('roas') or 0), a['metrics'].get('cpa') or math.inf, str(a['ad_id'])))), None)


def component_candidates(ads, kind, asset_rows=()):
    result = []
    breakdown = {'image': 'image_asset', 'primary_text': 'body_asset', 'headline': 'title_asset'}[kind]
    for ad in ads:
        for item in ad['assets'][kind]:
            direct = [row for row in asset_rows if str(row.get('ad_id')) == str(ad['ad_id'])
                      and row.get('breakdown') == breakdown and str(row.get('asset_key')) in {item['id'], item['value']}]
            metrics = aggregate([normalize_metrics(row.get('raw') or {}) for row in direct]) if direct else ad['metrics']
            result.append({**item, 'ad_id': ad['ad_id'], 'creative_id': ad['assets']['creative_id'],
                           'metrics': metrics, 'source': 'DIRECT META ASSET RESULT' if direct else 'INFERRED FROM WINNING ADS',
                           'evidence_dates': sorted({str(row.get('date') or (row.get('raw') or {}).get('date_start') or '') for row in direct}),
                           'last_observed': max((str(row.get('synced_at') or '') for row in direct),default=''),
                           'key': str(ad['ad_id']) + ':' + kind + ':' + item['id']})
    return result
