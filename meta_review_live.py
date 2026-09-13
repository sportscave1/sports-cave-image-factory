"""GET-only Meta Review reads. No database dependency or import-time requests."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import logging
import time

import meta_ads_client as meta
import meta_review_benchmarks as benchmarks

CAMPAIGN_FIELDS = 'id,name,status,effective_status,objective,created_time,updated_time,start_time,stop_time'
AD_FIELDS = ('id,name,status,effective_status,adset_id,creative{id,name,thumbnail_url,'
             'image_url,object_story_spec,asset_feed_spec},created_time,updated_time')
INSIGHT_FIELDS = ('date_start,date_stop,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,'
                  'spend,impressions,reach,frequency,clicks,ctr,cpc,cpm,inline_link_clicks,'
                  'inline_link_click_ctr,cost_per_inline_link_click,outbound_clicks,outbound_clicks_ctr,'
                  'actions,action_values,cost_per_action_type,purchase_roas,website_purchase_roas,cost_per_outbound_click')
CACHE_TTL = 120
CACHE_LIMIT = 24
REPORTABLE_CAMPAIGN_STATUSES = ('ACTIVE', 'PAUSED', 'ARCHIVED')
LOGGER = logging.getLogger(__name__)


def non_deleted(row):
    """Defensive exclusion for objects removed while paginated live reads run."""
    return all(str(row.get(key) or '').upper() != 'DELETED'
               for key in ('status', 'effective_status', 'configured_status'))


def safe_error(error):
    if isinstance(error, meta.MetaAdsApiError):
        return meta.sanitize_meta_error(str(error))[:350]
    if isinstance(error, ValueError):
        return meta.sanitize_meta_error(str(error))[:250]
    return 'The live Meta request could not be completed. Try Refresh From Meta again.'


def scope(config):
    """Isolate session caches across accounts, API versions and credential rotations."""
    token_hash = hashlib.sha256(str(config.get('access_token', '')).encode()).hexdigest()
    return (config.get('ad_account_id'), config.get('api_version'), token_hash)


def invalidate(cache, account_scope):
    # Keep the last successful response for an explicitly labelled stale fallback.
    for key, entry in cache.items():
        if key[0] == account_scope:
            entry['expires'] = 0


def cached_read(cache, key, loader, *, clock=time.monotonic):
    now = clock()
    old = cache.get(key, {})
    if old.get('expires', 0) > now:
        return deepcopy(old)
    try:
        data = loader()
        entry = {'data': data, 'refreshed_at': datetime.now(timezone.utc).isoformat(),
                 'error': '', 'stale': False}
    except Exception as error:
        entry = {'data': old.get('data'), 'refreshed_at': old.get('refreshed_at'),
                 'error': safe_error(error), 'stale': old.get('data') is not None}
    entry['expires'] = clock() + CACHE_TTL  # Also prevent failed-request rerun storms.
    cache[key] = entry
    while len(cache) > CACHE_LIMIT:
        del cache[next(iter(cache))]
    return deepcopy(entry)


class Reader:
    def __init__(self, config, *, max_pages=50, seconds=90):
        if not config.get('configured'):
            raise ValueError('Configure the existing Meta account connection before refreshing.')
        self.config = config
        self.max_pages = max_pages
        self.deadline = time.monotonic() + seconds

    def get(self, path, params):
        if time.monotonic() >= self.deadline:
            raise ValueError('Live Meta read reached its time limit. Narrow the date range or status.')
        # The existing client is GET-only, uses the configured API version and a 30s timeout.
        return meta._request(path, params=params, config=self.config)

    def pages(self, path, params):
        rows, seen = [], set()
        params = {**params, 'limit': 100}
        for _ in range(self.max_pages):
            payload = self.get(path, params)
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Meta returned an invalid live reporting response.')
            if any(not isinstance(row, dict) for row in payload['data']):
                raise ValueError('Meta returned an invalid reporting row.')
            rows.extend(row for row in payload['data'] if non_deleted(row))
            if len(rows) > self.max_pages * 100:
                raise ValueError('Live Meta result limit reached. Narrow the request.')
            paging = payload.get('paging') or {}
            if not paging.get('next'):
                return rows
            after = (paging.get('cursors') or {}).get('after')
            if not isinstance(after, str) or not after or after in seen:
                raise ValueError('Meta pagination did not advance. Refresh and try a narrower request.')
            seen.add(after)
            params['after'] = after  # Never follow arbitrary/token-bearing next URLs.
        raise ValueError('Live Meta page limit reached. Narrow the date range or status; partial results were not substituted.')


def date_params(since, until):
    if since is None:
        return {'date_preset': 'maximum'}
    if since > until:
        raise ValueError('Start date must precede end date.')
    return {'time_range': json.dumps({'since': str(since), 'until': str(until)})}


def load_campaigns(config, since, until, status='Active and paused'):
    if status in ('All', 'COMPLETED'):
        statuses = list(REPORTABLE_CAMPAIGN_STATUSES)
    elif status == 'Active and paused':
        statuses = ['ACTIVE', 'PAUSED']
    elif status in REPORTABLE_CAMPAIGN_STATUSES:
        statuses = [status]
    else:
        raise ValueError('Unsupported live campaign status. Use ACTIVE, PAUSED or ARCHIVED.')
    reader = Reader(config)
    account = reader.get(config['ad_account_id'], {'fields': 'account_id,name,currency,timezone_name'})
    if not isinstance(account, dict) or str(account.get('account_id')) != config['ad_account_id'].removeprefix('act_'):
        raise ValueError('Meta returned a different ad account. Check the existing account configuration.')
    params = {'fields': CAMPAIGN_FIELDS, **date_params(since, until)}
    params['effective_status'] = json.dumps(statuses)
    if status == 'COMPLETED':
        params['is_completed'] = 'true'
    rows = reader.pages(config['ad_account_id'] + '/campaigns', params)
    campaigns = {str(row['id']): {**row, 'campaign_id': str(row['id']), 'campaign_name': row.get('name'),
                                 'raw': row} for row in rows if row.get('id')}
    return {'account': account, 'campaigns': sorted(campaigns.values(), key=lambda r: (r.get('created_time') or '', r['campaign_id']), reverse=True)}


def filter_campaigns(rows, query='', status='All'):
    return [r for r in rows if non_deleted(r) and query.casefold() in str(r.get('campaign_name') or '').casefold()
            and (status in ('All', 'COMPLETED') or
                 (r.get('effective_status') or r.get('status')) in
                 (('ACTIVE', 'PAUSED') if status == 'Active and paused' else (status,)))]


def load_overview(config, since, until):
    """Campaign metadata plus one paginated account-level range report; no ad reads."""
    result = load_campaigns(config, since, until, status='All')
    fields = ','.join(field for field in INSIGHT_FIELDS.split(',')
                      if field not in ('ad_id','ad_name','adset_id','adset_name'))
    rows = Reader(config).pages(config['ad_account_id'] + '/insights', {
        'fields': fields, 'level': 'campaign', 'use_unified_attribution_setting': 'true',
        **date_params(since, until)})
    reports = {}
    for row in rows:
        key = str(row.get('campaign_id') or '')
        if not key:
            raise ValueError('Meta returned campaign Insights without a campaign identity.')
        if key in reports and reports[key] != row:
            raise ValueError('Meta returned conflicting campaign range reports. Refresh again.')
        reports[key] = row
    countries = load_countries(config, config['ad_account_id'], 'campaign', since, until)
    for campaign in result['campaigns']:
        metrics = benchmarks.graph_metrics(reports.get(campaign['campaign_id'], {}))
        # This overview explicitly promises Meta-reported ROAS, not a synthesized ratio.
        metrics['roas'] = metrics['reported_roas']
        campaign['metrics'] = metrics
        campaign['benchmark'] = benchmarks.evaluate(metrics,country=benchmarks.market([
            r for r in countries if str(r.get('campaign_id'))==campaign['campaign_id']]),
            currency=result['account'].get('currency','UNKNOWN'))
    return result


def load_countries(config, identity, level, since, until):
    # Separate delivery-only report: never sum broken-down reach/conversions into totals.
    try:
        return Reader(config).pages(str(identity)+'/insights', {
            'fields': level+'_id,spend', 'level':level, 'breakdowns':'country',
            'use_unified_attribution_setting':'true', **date_params(since,until)})
    except meta.MetaAdsApiError as error:
        message=str(error).lower()
        compatibility_error=(str(error.error_code)=='100'
            and any(word in message for word in ('country','breakdown'))
            and any(word in message for word in ('not supported','unsupported','not valid','invalid','combination','cannot be combined'))
            and not any(word in message for word in ('permission','access token','authentication','authorization')))
        if not compatibility_error:
            raise
        # Discard the whole supplemental result, including any successful earlier
        # pages. Partial country coverage could incorrectly select a single market.
        LOGGER.warning('Meta Review country breakdown unavailable; market UNKNOWN; primary metrics retained (code=%s, subcode=%s)',
                       error.error_code,error.error_subcode)
        return []


def load_campaign(config, campaign_id, since, until):
    if not str(campaign_id).isdigit():
        raise ValueError('Select a valid live Meta campaign.')
    reader = Reader(config)
    rows = reader.pages(str(campaign_id) + '/ads', {'fields': AD_FIELDS})
    sets = reader.pages(str(campaign_id) + '/adsets', {'fields': 'id,name,status,effective_status,targeting'})
    insights = reader.pages(str(campaign_id) + '/insights', {'fields': INSIGHT_FIELDS,
        'level': 'ad', 'use_unified_attribution_setting': 'true', **date_params(since, until)})
    ads = {}
    creatives = {}
    for row in rows:
        if not row.get('id'):
            raise ValueError('Meta returned an ad without an identity.')
        creative = row.get('creative') if isinstance(row.get('creative'), dict) else {}
        ads[str(row['id'])] = {**row, 'ad_id': str(row['id']), 'ad_name': row.get('name'),
            'campaign_id': str(campaign_id), 'creative_id': str(creative.get('id') or ''), 'raw': row}
        if creative.get('id'):
            creatives[str(creative['id'])] = {'creative_id': str(creative['id']), 'raw': creative}
    # Insights is a single range report per ad: do not sum unique reach across days.
    metrics = {}
    for row in insights:
        if not row.get('ad_id'):
            raise ValueError('Meta returned Insights without an ad identity.')
        key = str(row['ad_id'])
        if key in metrics and metrics[key]['raw'] != row:
            raise ValueError('Meta returned conflicting range reports for an ad. Refresh the campaign.')
        metrics[key] = {'ad_id': key, 'date': row.get('date_start') or str(since or until), 'raw': row}
    country_rows = load_countries(config,campaign_id,'ad',since,until)
    return {'ads': list(ads.values()), 'creatives': list(creatives.values()), 'daily': list(metrics.values()),
        'adsets': [{**r, 'adset_id': str(r['id']), 'adset_name': r.get('name'), 'raw': r} for r in sets if r.get('id')],
        'country_delivery':country_rows,
        'assets': [], 'observations': [], 'selections': [], 'mapping': [], 'logs': [], 'campaigns': [], 'accounts': []}
