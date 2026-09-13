"""Explicit GET-only Meta Review sync; shared credentials/client, bounded pagination."""
import json
import logging
import time
from urllib.parse import urlparse

import meta_ads_client as meta
import meta_review_store as store

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
    return 'Reporting storage is unavailable or its migration is missing. Check server/database configuration; prior history has been retained.'


class Reader:
    def __init__(self, config, seconds=180, max_pages=50):
        self.config = config
        self.deadline = time.monotonic() + seconds
        self.max_pages = max_pages

    def get(self, path, params):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Meta sync time limit reached. Select a shorter date range and retry. History was retained.')
        # Existing client uses a 30s request timeout. Total sync <= deadline + one request.
        for attempt in range(2):
            try:
                return meta._request(path, params=params, config=self.config)
            except meta.MetaAdsApiError as error:
                if attempt or error.status_code not in (502, 503, 504) or time.monotonic() >= self.deadline:
                    raise

    def pages(self, path, params):
        rows, afters = [], set()
        params = {**params, 'limit': 100}
        for _ in range(self.max_pages):
            payload = self.get(path, params)
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Meta returned malformed reporting data. History was retained.')
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
        statuses = json.dumps(['ACTIVE','PAUSED','ARCHIVED','DELETED'])
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
        adsets = reader.pages(config['ad_account_id']+'/adsets', {'fields': 'id,name,campaign_id,status,effective_status,targeting,created_time,updated_time', 'effective_status':json.dumps(['ACTIVE','PAUSED','ARCHIVED','DELETED','CAMPAIGN_PAUSED','IN_PROCESS','WITH_ISSUES'])})
        progress('Reading actual ads and creative assets…')
        base_ads = 'id,name,campaign_id,adset_id,status,effective_status,created_time,updated_time'
        try:
            ads = reader.pages(config['ad_account_id']+'/ads', {'fields': base_ads+',creative{'+CREATIVE+'}', 'effective_status':json.dumps(['ACTIVE','PAUSED','ARCHIVED','DELETED','CAMPAIGN_PAUSED','ADSET_PAUSED','DISAPPROVED','PENDING_REVIEW','IN_PROCESS','WITH_ISSUES'])})
        except meta.MetaAdsApiError as error:
            if not optional_error(error):
                raise
            ads = reader.pages(config['ad_account_id']+'/ads', {'fields': base_ads+',creative{id,name,thumbnail_url,object_story_spec,asset_feed_spec}', 'effective_status':json.dumps(['ACTIVE','PAUSED','ARCHIVED','DELETED','CAMPAIGN_PAUSED','ADSET_PAUSED'])})
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
