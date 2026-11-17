"""Explicit GET-only Meta Review sync; shared credentials/client, bounded pagination."""
import json
import logging
import time
from urllib.parse import urlparse

import meta_ads_client as meta
import meta_review_retry as retry
import meta_review_store as store
from datetime import datetime, timezone
from meta_reporting_contract import (REPORTABLE_CAMPAIGN_STATUSES, REPORTABLE_ADSET_STATUSES,
                                     REPORTABLE_AD_STATUSES, reporting_window, validate_account)

LOGGER=logging.getLogger(__name__)

CORE = ('date_start,date_stop,account_id,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,'
        'spend,impressions,reach,clicks,inline_link_clicks,frequency,actions,action_values,purchase_roas')
OPTIONAL = 'instant_experience_clicks_to_open,instant_experience_clicks_to_start,instant_experience_outbound_clicks,outbound_clicks'
BREAKDOWNS = ('image_asset', 'body_asset', 'title_asset', 'description_asset', 'video_asset', 'call_to_action_asset')
CREATIVE = 'id,name,body,title,image_url,thumbnail_url,image_hash,video_id,object_story_spec,asset_feed_spec,call_to_action_type,link_url,effective_object_story_id'


def safe_error(error):
    if isinstance(error, meta.MetaAdsApiError):
        return meta.sanitize_meta_error(str(error))[:500]
    if isinstance(error, (TimeoutError, ValueError)):
        return str(error)[:250]
    return 'Reporting storage is unavailable or save completion could not be confirmed. Check sync history and server/database configuration before retrying.'


class Reader:
    def __init__(self, config, seconds=180, max_pages=50):
        self.config = config
        self.deadline = time.monotonic() + seconds
        self.max_pages = max_pages

    def get(self, path, params):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Meta sync time limit reached. Select a shorter date range and retry. History was retained.')
        return retry.get(path, params, self.config, self.deadline)

    def pages(self, path, params):
        rows, afters = [], set()
        params = {**params, 'limit': 100}
        for _ in range(self.max_pages):
            payload = self.get(path, params)
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Meta returned malformed reporting data. History was retained.')
            if any(not isinstance(row, dict) for row in payload['data']):
                raise ValueError('Meta returned malformed reporting rows. History was retained.')
            rows.extend(payload['data'])
            paging = payload.get('paging') or {}
            if not paging.get('next'):
                return rows
            after = (paging.get('cursors') or {}).get('after')
            if not after or after in afters:
                raise ValueError('Meta pagination did not advance. Retry a smaller sync.')
            afters.add(after)
            params['after'] = after  # Never follow a token-bearing arbitrary next URL.
        raise ValueError('Meta page limit reached. Select a smaller range; incomplete history was not saved.')


def optional_error(error):
    return isinstance(error, meta.MetaAdsApiError) and str(error.error_code) in ('100', '3')


def collect_reporting(since=None, until=None, *, days=None, config=None, reader=None, at=None):
    """GET-only preparation; no log, schema, cache or database writes."""
    config = config or meta.get_meta_config()
    if not config.get('configured'):
        raise ValueError('Configure the existing Meta account connection before refreshing.')
    reader = reader or Reader(config)
    aid = str(config['ad_account_id']).removeprefix('act_')
    account = validate_account(reader.get(config['ad_account_id'],
        {'fields': 'account_id,name,currency,timezone_name'}), aid)
    since, until = reporting_window(account, since, until, days=days, at=at)
    params = {'fields': CORE, 'level': 'ad', 'time_increment': 1,
              'time_range': json.dumps({'since': since, 'until': until}),
              'use_unified_attribution_setting': 'true', 'action_report_time': 'impression'}
    daily = reader.pages(config['ad_account_id']+'/insights', params)
    unique = {}
    for row in daily:
        if (str(row.get('account_id')) != aid or not row.get('ad_id')
                or row.get('date_start') != row.get('date_stop')
                or not since <= str(row.get('date_start', '')) <= until):
            raise ValueError('Meta returned a different account, grain or date; history was retained.')
        key = (row['date_start'], str(row['ad_id']))
        if key in unique and unique[key] != row:
            raise ValueError('Meta returned conflicting duplicate daily rows; history was retained.')
        unique[key] = row
    captured = datetime.now(timezone.utc).isoformat()
    return {'account_id': aid, 'account': account, 'campaigns': [], 'adsets': [], 'ads': [],
            'daily': list(unique.values()), 'assets': [], 'warnings': [],
            'api_version': config['api_version'],
            'reporting': {'since': since, 'until': until, 'timezone': account['timezone_name'],
                          'currency': account['currency'], 'level': 'ad', 'time_increment': 1,
                          'complete': True, 'captured_at': captured, 'api_version': config['api_version'],
                          'use_unified_attribution_setting': True, 'action_report_time': 'impression',
                          'attribution_windows': 'Per-adset settings; exact windows not returned by this query.'}}


def sync_reporting(since=None, until=None, *, days=None, config=None, reader=None):
    """Explicit manual refresh into the existing Daily Brief source tables."""
    config = config or meta.get_meta_config()
    if not config.get('configured'):
        raise ValueError('Configure the existing Meta account connection before refreshing.')
    aid = str(config['ad_account_id']).removeprefix('act_')
    log_id = store.log_start(aid, f'Completed daily performance: {since or days or 1} / {until or ""}')
    try:
        payload = collect_reporting(since, until, days=days, config=config, reader=reader)
        counts = store.save_sync(payload, log_id)
        return {'counts': counts, 'warnings': payload['warnings'], 'reporting': payload['reporting']}
    except Exception as error:
        message = safe_error(error)
        try:
            store.log_failure(log_id, message)
        except Exception:
            LOGGER.error('Meta reporting failure log unavailable sync_id=%s', log_id)
        raise RuntimeError(message) from None


def sync(since=None, until=None, *, lifetime=False, assets=True, progress=lambda message: None, reader=None):
    config = meta.get_meta_config()
    if not config['configured']:
        raise ValueError('Configure META_ACCESS_TOKEN and META_AD_ACCOUNT_ID before syncing.')
    aid = config['ad_account_id'].removeprefix('act_')
    label = 'Available Meta history' if lifetime else f'{since} — {until}'
    log_id = store.log_start(aid, label)
    reader = reader or Reader(config)
    try:
        progress('Reading account and campaign history…')
        warnings = []
        account = reader.get(config['ad_account_id'], {'fields': 'account_id,name,currency,timezone_name'})
        statuses = json.dumps(REPORTABLE_CAMPAIGN_STATUSES)
        campaigns = reader.pages(config['ad_account_id']+'/campaigns', {'fields': 'id,name,status,effective_status,objective,created_time,updated_time', 'effective_status':statuses})
        try:
            completed = reader.pages(config['ad_account_id']+'/campaigns', {'fields':'id,name,status,effective_status,objective,created_time,updated_time','is_completed':'true'})
            merged = {str(c['id']): c for c in campaigns}
            for c in completed:
                merged[str(c['id'])] = {**c,'_review_completed':True}
            campaigns = list(merged.values())
        except meta.MetaAdsApiError as error:
            if not optional_error(error): raise
            warnings.append('Completed-campaign filter unavailable; accessible archived/paused history retained.')
        adsets = reader.pages(config['ad_account_id']+'/adsets', {'fields': 'id,name,campaign_id,status,effective_status,targeting,created_time,updated_time', 'effective_status':json.dumps(REPORTABLE_ADSET_STATUSES)})
        progress('Reading actual ads and creative assets…')
        base_ads = 'id,name,campaign_id,adset_id,status,effective_status,created_time,updated_time'
        try:
            ads = reader.pages(config['ad_account_id']+'/ads', {'fields': base_ads+',creative{'+CREATIVE+'}', 'effective_status':json.dumps(REPORTABLE_AD_STATUSES)})
        except meta.MetaAdsApiError as error:
            if not optional_error(error):
                raise
            ads = reader.pages(config['ad_account_id']+'/ads', {'fields': base_ads+',creative{id,name,thumbnail_url,object_story_spec,asset_feed_spec}', 'effective_status':json.dumps(REPORTABLE_AD_STATUSES)})
            warnings.append('Some optional creative fields were unsupported. Available original assets are retained.')
        # Resolve dynamic image hashes using the same account endpoint when URLs are absent.
        hashes = set()
        for ad in ads:
            creative = ad.get('creative') or {}
            for img in (creative.get('asset_feed_spec') or {}).get('images') or []:
                if isinstance(img, dict) and img.get('hash') and not img.get('url'):
                    hashes.add(img['hash'])
        images = {}
        if hashes:
            for offset in range(0, len(hashes), 50):
                for img in reader.pages(config['ad_account_id']+'/adimages', {'fields': 'hash,url', 'hashes': json.dumps(sorted(hashes)[offset:offset+50])}):
                    images[img['hash']] = img.get('url')
            for ad in ads:
                for img in ((ad.get('creative') or {}).get('asset_feed_spec') or {}).get('images') or []:
                    if isinstance(img, dict) and not img.get('url'):
                        img['url'] = images.get(img.get('hash'))
        progress('Reading daily commercial results…')
        dates = {'date_preset': 'maximum'} if lifetime else {'time_range': json.dumps({'since': str(since), 'until': str(until)})}
        params = {'level': 'ad', 'time_increment': 1, **dates}
        path = config['ad_account_id']+'/insights'
        try:
            daily = reader.pages(path, {**params, 'fields': CORE+','+OPTIONAL})
        except meta.MetaAdsApiError as error:
            if not optional_error(error):
                raise
            daily = reader.pages(path, {**params, 'fields': CORE})
            warnings.append('Optional Instant Experience/outbound fields unavailable; displayed as unavailable.')
        asset_rows = []
        if assets:
            for breakdown in BREAKDOWNS:
                progress('Checking '+breakdown.replace('_', ' ')+' attribution…')
                try:
                    rows = reader.pages(path, {**params, 'fields': 'ad_id,date_start,date_stop,spend,impressions,inline_link_clicks,actions,action_values,purchase_roas', 'breakdowns': breakdown})
                except meta.MetaAdsApiError as error:
                    if not optional_error(error):
                        raise
                    warnings.append(breakdown+' unavailable: component evidence is inferred from complete ads.')
                    continue
                for row in rows:
                    asset = row.get(breakdown)
                    if not isinstance(asset, dict):
                        continue
                    key = asset.get('hash') or asset.get('text') or asset.get('id') or asset.get('url')
                    if key is not None:
                        asset_rows.append({'ad_id': str(row['ad_id']), 'date': row['date_start'],
                            'breakdown': breakdown, 'asset_key': str(key), 'raw': row})
        progress('Committing reporting history to Supabase…')
        counts = store.save_sync(dict(account_id=aid, account=account, campaigns=campaigns, adsets=adsets,
                                     ads=ads, daily=daily, assets=asset_rows, warnings=warnings, api_version=config['api_version']), log_id)
        return {'counts': counts, 'warnings': warnings}
    except Exception as error:
        message = safe_error(error)
        LOGGER.error('Meta Review sync failed account=%s sync_id=%s reason=%s',aid,log_id,message)
        try:
            store.log_failure(log_id, message)
        except Exception:
            LOGGER.error('Meta Review could not persist the failure log account=%s sync_id=%s',aid,log_id)
        raise RuntimeError(message) from None
