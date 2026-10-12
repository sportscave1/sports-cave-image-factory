"""On-demand Google reporting. Memory only: no reporting database reads/writes."""
from __future__ import annotations

from collections import OrderedDict, deque
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import threading
import time
from zoneinfo import ZoneInfo

import requests
import analytics_contracts
import analytics_reporting
import google_seo
import google_seo_import
import seo_metrics

GA4_TTL = 20 * 60
GSC_TTL = 8 * 60 * 60
GSC_PAGE_SIZE = 25000
GSC_MAX_PAGES = 8


class DirectReportingError(analytics_reporting.AnalyticsReportingError):
    pass


class MemoryReports:
    """Bounded process cache; single flight also bounds concurrent Google calls."""
    def __init__(self, *, clock=time.monotonic, max_bytes=32 * 1024 * 1024):
        self.clock, self.max_bytes = clock, max_bytes
        self.entries = OrderedDict()
        self.lock = threading.RLock()
        self.size = 0
        self.cooldowns = {}
        self.request_times = {}
        self.generation = 0

    def read(self, key, ttl, fetch):
        with self.lock:
            now = self.clock()
            for old in list(self.entries):
                expires, value, size = self.entries[old]
                if expires <= now:
                    self.entries.pop(old)
                    self.size -= size
            if key in self.entries:
                self.entries.move_to_end(key)
                return deepcopy(self.entries[key][1])
            value = fetch()
            size = len(json.dumps(value, default=str).encode())
            if size <= self.max_bytes:
                while self.entries and (self.size + size > self.max_bytes or len(self.entries) >= 128):
                    _, (_, _, removed) = self.entries.popitem(last=False)
                    self.size -= removed
                self.entries[key] = (self.clock() + ttl, deepcopy(value), size)
                self.size += size
            return value

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.size = 0
            self.generation += 1
            # Explicit refresh must not bypass quota/error cooldowns.


REPORTS = MemoryReports()


class DirectTransport(google_seo_import.GoogleSEOReportingClient):
    """No automatic report retries; respect throttling across report contracts."""
    def __init__(self, token, scope, *, cache=REPORTS):
        super().__init__(token)
        self.scope, self.cache = scope, cache

    def _post(self, endpoint, payload, *, stage):
        with self.cache.lock:
            now = self.cache.clock()
            cooldown = self.cache.cooldowns.get(self.scope, 0)
            if now < cooldown:
                raise DirectReportingError('Google reporting is temporarily unavailable. Try again after the quota cooldown.', code='google_reporting_cooldown')
            recent = self.cache.request_times.setdefault(self.scope, deque())
            while recent and now - recent[0] >= 60:
                recent.popleft()
            if len(recent) >= 120:
                raise DirectReportingError('Google report request budget reached. Wait a minute before refreshing.', code='google_reporting_rate_limit')
            recent.append(now)
            try:
                response = self.request_post(endpoint, headers=self.headers, json=payload, timeout=(5, 25))
            except requests.RequestException as error:
                self.cache.cooldowns[self.scope] = now + 60
                raise DirectReportingError('Google reporting request timed out. Try again shortly.', code='google_reporting_network') from error
            if response.status_code >= 400:
                try:
                    retry_after = max(60, min(3600, int(response.headers.get('Retry-After', 60))))
                except (TypeError, ValueError):
                    retry_after = 60
                self.cache.cooldowns[self.scope] = now + (retry_after if response.status_code == 429 else 60)
                raise DirectReportingError(
                    'Google reporting is unavailable. Check the connection and property permissions.' if response.status_code in (401, 403) else 'Google reporting is temporarily unavailable. Try again shortly.',
                    code=f'google_reporting_http_{response.status_code}', retryable=response.status_code in (429, 500, 502, 503, 504))
            result = google_seo._response_json(response, stage=stage)
            quota = result.get('propertyQuota') or {}
            if any(int((quota.get(name) or {}).get('remaining', 100)) < 10 for name in ('tokensPerDay', 'tokensPerHour', 'tokensPerProjectPerHour')) or int((quota.get('serverErrorsPerProjectPerHour') or {}).get('remaining', 10)) <= 1:
                self.cache.cooldowns[self.scope] = now + 3600
            return result


class GoogleReports:
    def __init__(self, *, connection_store=None, cache=REPORTS, client_factory=None):
        self.store = connection_store or google_seo.default_store()
        self.cache, self.client_factory = cache, client_factory

    def connection(self):
        try:
            return self.store.get_connection()
        except Exception as error:
            raise DirectReportingError('The Google connection settings could not be read.', code='google_connection_unavailable') from error

    @staticmethod
    def identity(connection):
        return tuple(google_seo._iso(connection.get(key)) if key.endswith('_at') else str(connection.get(key) or '') for key in ('id', 'workspace_key', 'connected_at', 'updated_at', 'gsc_site_url', 'ga4_property_id', 'disconnected_at'))

    def client(self, connection):
        if self.client_factory:
            return self.client_factory(connection)
        identity = self.identity(connection)
        def token():
            access, selected = google_seo.access_token_for_connection(self.store, google_seo.load_config())
            if self.identity(self.connection()) != identity or any(selected.get(key) != connection.get(key) for key in ("gsc_site_url", "ga4_property_id")):
                raise DirectReportingError('Google connection changed. Refresh this page.', code='google_connection_changed')
            return access
        try:
            access = self.cache.read(('token', identity), 45 * 60, token)
        except google_seo.GoogleSEOError as error:
            raise DirectReportingError('Google authentication failed. Check or reconnect the existing Google connection.', code=error.code, retryable=False) from error
        return DirectTransport(access, identity, cache=self.cache)

    def ga4(self, property_id, contract_key, start, end, *, filters=()):
        connection = self.connection()
        selected = analytics_reporting.CanonicalGA4Client._property(connection.get('ga4_property_id'))
        if not connection.get('ga4_property_id') or selected != analytics_reporting.CanonicalGA4Client._property(property_id):
            raise DirectReportingError('Select the connected GA4 property.', code='google_property_mismatch', retryable=False)
        contract = analytics_contracts.report_contract(contract_key) if isinstance(contract_key, str) else contract_key
        start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        if start > end:
            raise ValueError('Start date must precede end date.')
        key = ('ga4', self.identity(connection), contract, start, end, tuple(filters))
        def fetch():
            report = analytics_reporting.CanonicalGA4Client('', reporting_client=self.client(connection)).fetch_report(property_id, contract, start, end, filters=filters, currency=connection.get('ga4_property_currency') or '')
            report['metadata']['quality'] = report['quality']
            report['quality_status'] = report['quality']['status']
            if not report['complete']:
                raise DirectReportingError('This report exceeds the safe row limit. Narrow the date range.', code='google_report_incomplete', retryable=False)
            return report
        return self.cache.read(key, GA4_TTL, fetch)

    def gsc(self, start, end, dimensions, filters):
        connection = self.connection()
        site = connection.get('gsc_site_url')
        if not site:
            raise DirectReportingError('Select a Search Console property.', code='gsc_property_required', retryable=False)
        start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        today = datetime.now(ZoneInfo('America/Los_Angeles')).date()
        # Search Console cannot restore old retained database history.
        import seo_live_analytics
        if start < seo_live_analytics._shift_months(today, -16):
            raise DirectReportingError('This range is outside Search Console’s available history. Retained historical exports are required.', code='gsc_history_unavailable', retryable=False)
        if start > end:
            raise ValueError('Start date must precede end date.')
        clauses = list(filters.get('extra_filters') or ())
        market = filters.get('market', 'All markets')
        countries = {'AU': 'aus', 'Australia': 'aus', 'US': 'usa', 'United States': 'usa', 'UK': 'gbr', 'United Kingdom': 'gbr'}
        if market != 'All markets':
            if market not in countries:
                raise ValueError('Unsupported Search Console market.')
            clauses.append({'dimension': 'country', 'operator': 'equals', 'expression': countries[market]})
        device = filters.get('device', 'All devices')
        if device != 'All devices':
            clauses.append({'dimension': 'device', 'operator': 'equals', 'expression': device.lower()})
        query_class = filters.get('query_class', 'All known queries')
        if query_class in ('Branded', 'Non-branded'):
            import re
            terms = filters.get('brand_terms') or ('sports cave', 'sportscave')
            clauses.append({'dimension': 'query', 'operator': 'includingRegex' if query_class == 'Branded' else 'excludingRegex', 'expression': '(?i)(' + '|'.join(re.escape(term) for term in terms) + ')'})
        payload = {'startDate': start.isoformat(), 'endDate': end.isoformat(), 'dimensions': list(dimensions), 'type': filters.get('search_type') or 'web', 'dataState': 'all' if filters.get('preset') == 'Today' else 'final', 'aggregationType': 'auto' if 'page' in dimensions or any(c.get('dimension') == 'page' for c in clauses) else 'byProperty', 'rowLimit': GSC_PAGE_SIZE}
        if clauses:
            payload['dimensionFilterGroups'] = [{'groupType': 'and', 'filters': clauses}]
        key = ('gsc', self.identity(connection), json.dumps(payload, sort_keys=True))
        def fetch():
            client = self.client(connection)
            rows = []
            seen = set()
            for page in range(GSC_MAX_PAGES):
                result = client._post(client._gsc_endpoint(site), {**payload, 'startRow': len(rows)}, stage='gsc_direct')
                batch = result.get('rows') or []
                fingerprint = hashlib.sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()
                if batch and fingerprint in seen:
                    raise DirectReportingError('Google returned a repeated page. Narrow the date range.', code='gsc_pagination_repeated')
                seen.add(fingerprint)
                for row in batch:
                    values = dict(zip(dimensions, row.get('keys') or []))
                    impressions = Decimal(str(row.get('impressions') or 0))
                    rows.append({**values, 'clicks': Decimal(str(row.get('clicks') or 0)), 'impressions': impressions, 'position_weight': Decimal(str(row.get('position') or 0)) * impressions, 'average_position': Decimal(str(row.get('position') or 0)), 'ctr': Decimal(str(row.get('ctr') or 0))})
                if len(batch) < GSC_PAGE_SIZE:
                    return rows
            raise DirectReportingError('This Search Console report exceeds the safe row limit. Narrow the date range.', code='gsc_report_incomplete', retryable=False)
        return self.cache.read(key, GSC_TTL, fetch)


class DirectAnalyticsStore:
    def __init__(self, reports=None):
        self.reports = reports or GoogleReports()

    def report_for_period(self, property_id, contract_key, start, end):
        return self.reports.ga4(property_id, contract_key, start, end)

    def latest_report(self, property_id, contract_key):
        if contract_key != 'realtime':
            return {}
        today = date.today()
        return self.report_for_period(property_id, contract_key, today, today)

    def queue_report(self, *args, **kwargs):
        return {'status': 'disabled', 'reason': 'direct_google_reporting'}


def disabled_import():
    return {'status': 'disabled', 'reason': 'direct_google_reporting'}

class DirectSEOReader:
    """Existing SEO view contracts, calculated from cached Google aggregates."""
    def __init__(self, reports=None, settings_store=None):
        self.reports = reports or GoogleReports()
        self.settings_store = settings_store
        self.notices = set()
        self.diagnostics = {'reader_path': 'google_direct', 'query_count': 0, 'query_ms': 0, 'rows_returned': 0}

    def _filters(self, filters):
        import google_seo_phase4
        store = self.settings_store or google_seo_phase4.default_phase4_store()
        settings = store.get_settings()
        return {**filters, 'brand_terms': settings.get('brand_terms') or ('sports cave', 'sportscave')}

    def reporting_context(self):
        connection = self.reports.connection()
        today = datetime.now(ZoneInfo('America/Los_Angeles')).date()
        available = bool(connection.get('gsc_site_url'))
        # Discover the final-data watermark on demand, never on application startup.
        through = ''
        if available:
            days = self.reports.gsc(today - timedelta(days=10), today, ('date',), {})
            through = max((row['date'] for row in days), default='')
        return {'available': available, 'status': 'google_direct' if available else 'not_configured', 'reader_path': 'google_direct', 'through_date': through or (today - timedelta(days=3)).isoformat(), 'gsc_site_url': connection.get('gsc_site_url') or '', 'ga4_property_id': connection.get('ga4_property_id') or '', 'watermark': hashlib.sha256(repr((self.reports.identity(connection), int(time.time() // GSC_TTL), self.reports.cache.generation)).encode()).hexdigest(), 'source_revision': 0}

    @staticmethod
    def period(filters, context):
        import seo_reporting_runtime
        return seo_reporting_runtime.PostgresSEOInteractiveReader.period(filters, context)

    @staticmethod
    def _health(context):
        return {'gsc': {'available': context['available'], 'status': context['status'], 'through_date': context['through_date'], 'identifier': context['gsc_site_url'], 'reader_path': 'google_direct', 'source_label': 'Google Search Console API', 'snapshot_pending': False}, 'snapshot': context}

    def _period_rows(self, filters, context, dimensions, previous=False):
        period = self.period(filters, context)
        if not period:
            raise ValueError('Choose a valid date range.')
        prefix = 'previous_' if previous else ''
        start, end = period.get(prefix + 'start_date'), period.get(prefix + 'end_date')
        if not start or not end:
            return []
        import seo_live_analytics
        earliest = seo_live_analytics._shift_months(datetime.now(ZoneInfo('America/Los_Angeles')).date(), -16)
        if start < earliest:
            if previous:
                self.notices.add('The comparison falls outside Google?s retained history and is unavailable.')
                return []
            if filters.get('preset') == 'Last 16 months':
                start = earliest
                self.notices.add('This range begins at Google?s earliest available date.')
        return self.reports.gsc(start, end, dimensions, filters)

    @staticmethod
    def _totals(rows):
        clicks = sum((row['clicks'] for row in rows), Decimal(0))
        impressions = sum((row['impressions'] for row in rows), Decimal(0))
        weight = sum((row['position_weight'] for row in rows), Decimal(0))
        return {'organic_clicks': clicks, 'organic_impressions': impressions, 'ctr': clicks / impressions if impressions else Decimal(0), 'average_position': weight / impressions if impressions else None}

    def _queries(self, filters, context):
        rows = seo_metrics.aggregate_query_rows(self._period_rows(filters, context, ('query', 'country', 'device')))
        previous = {row['normalized_query']: row for row in seo_metrics.aggregate_query_rows(self._period_rows(filters, context, ('query', 'country', 'device'), True))}
        result = []
        for row in rows:
            prior = previous.get(row['normalized_query'], {})
            old_position = prior.get('average_position')
            change = row['clicks'] - prior.get('clicks', 0)
            item = {**row, 'query_key': seo_metrics.normalize_query(row['query']), 'previous_clicks': prior.get('clicks', 0), 'previous_impressions': prior.get('impressions', 0), 'previous_position': old_position, 'click_change': change, 'ranking_change': old_position - row['average_position'] if old_position is not None else None, 'market_mix': row.get('market_mix', []), 'device_mix': row.get('device_mix', []), 'current_page': '', 'canonical_page_key': '', 'mapped_page_count': 0}
            item['opportunity_score'] = seo_metrics.opportunity_score(item)['score']
            result.append(item)
        return result

    def overview_base(self, filters, *, context=None):
        context = context or self.reporting_context()
        filters = self._filters(filters)
        rows = self._period_rows(filters, context, ('date',))
        previous = self._period_rows(filters, context, ('date',), True)
        queries = self._queries(filters, context)
        return {'ready': context['available'], 'reason': '', 'health': self._health(context), 'filters': filters, 'period': {k: str(v) if v is not None else None for k, v in self.period(filters, context).items()}, 'current': self._totals(rows), 'previous': self._totals(previous) if previous else {}, 'daily_trend': [{'date': row['date'], **self._totals([row])} for row in rows], 'previous_daily_trend': [{'date': row['date'], **self._totals([row])} for row in previous], 'top_queries': queries, 'rank_quality': seo_metrics.rank_quality(queries), 'known_query_clicks': sum((row['clicks'] for row in queries), Decimal(0)), 'known_query_impressions': sum((row['impressions'] for row in queries), Decimal(0)), 'watermark': context['watermark'], 'fallback_mode': False, 'summary_dataset': 'property_totals' if filters.get('query_class') not in ('Branded', 'Non-branded') else 'query_dimensions', 'diagnostics': self.diagnostics, 'data_note': 'Search Console omits anonymised queries and may return only top rows. Keyword coverage is separate from property totals. ' + ' '.join(sorted(self.notices))}

    def query_page(self, filters, *, view='All', search='', limit=25, cursor=None, context=None, excluded_queries=(), _export_all=False):
        context = context or self.reporting_context()
        rows = self._queries(self._filters(filters), context)
        excluded = {seo_metrics.normalize_query(q) for q in excluded_queries} if view in ('Unmapped', 'Opportunities') else set()
        def include(row):
            position = row['average_position']
            change = row['ranking_change'] or 0
            matches = {'Quick wins': 4 <= position <= 20, 'Opportunities': 4 <= position <= 20, 'Rising': change > 0, 'Declining': change < 0, 'New': not row['previous_impressions'] and not self.notices, 'Top 3': 0 < position <= 3, 'Positions 4-10': 4 <= position <= 10, 'Positions 11-20': 11 <= position <= 20, 'Unmapped': not row['canonical_page_key']}
            return matches.get(view, True) and search.casefold() in row['query'].casefold() and row['query_key'] not in excluded
        rows = [row for row in rows if include(row)]
        for row in rows:
            row['sort_score'] = {'Rising': row['ranking_change'] or 0, 'Declining': -(row['ranking_change'] or 0), 'Quick wins': row['opportunity_score'], 'Opportunities': row['opportunity_score'], 'New': row['impressions']}.get(view, row['clicks'])
        def order(row):
            return (-Decimal(str(row['sort_score'])), -Decimal(str(row['impressions'])), row['query'])
        rows.sort(key=order)
        total = len(rows)
        if cursor:
            rows = [row for row in rows if order(row) > order(cursor)]
        selected = rows if _export_all else rows[:max(1, min(100, int(limit)))]
        last = selected[-1] if selected and len(selected) < len(rows) else None
        return {'rows': selected, 'total': total, 'next_cursor': {k: last[k] for k in ('sort_score', 'impressions', 'query')} if last else None, 'unavailable': False, 'diagnostics': self.diagnostics}

    def query_export(self, filters, **kwargs):
        return self.query_page(filters, _export_all=True, **kwargs)

    def rank_distribution(self, filters, *, context=None):
        context = context or self.reporting_context()
        return {**seo_metrics.rank_quality(self._queries(self._filters(filters), context)), 'unavailable': False, 'diagnostics': self.diagnostics}

    def landing_pages(self, filters, *, limit=25, context=None):
        from urllib.parse import urlsplit
        import seo_live_analytics
        context = context or self.reporting_context()
        filters = self._filters(filters)
        rows = self._period_rows(filters, context, ('page',))
        old = {row['page']: row for row in self._period_rows(filters, context, ('page',), True)}
        # Existing page titles are Sports Cave-owned metadata, not reporting facts.
        metadata_reader = seo_live_analytics.PostgresSEOLiveAnalyticsReader(self.settings_store)
        paths = [urlsplit(row['page']).path or '/' for row in rows]
        metadata = metadata_reader._canonical_metadata(paths)
        ga4 = {}
        notice = ''
        if context.get('ga4_property_id'):
            period = self.period(filters, context)
            try:
                report = self._organic_ga4(context, period, filters, ('landingPagePlusQueryString',))
                for item in report['rows']:
                    path = item['dimensions'].get('landingPagePlusQueryString', '').split('?', 1)[0]
                    metrics = ga4.setdefault(path, {'sessions': Decimal(0)})
                    metrics['sessions'] += Decimal(item['metrics'].get('sessions') or 0)
            except DirectReportingError as error:
                notice = 'Search Console pages are available. Supporting GA4 sessions are unavailable: ' + error.public_message
        result = []
        for row in rows:
            path = urlsplit(row['page']).path or '/'
            saved = metadata.get(path, {})
            metrics = ga4.get(path, {})
            result.append({**row, 'page_url': row['page'], 'canonical_url': row['page'], 'path': path, 'title': saved.get('title') or '', 'page_type': saved.get('page_type') or seo_live_analytics._page_type(path), 'previous_change': row['clicks'] - old.get(row['page'], {}).get('clicks', 0), 'sessions': Decimal(metrics['sessions']) if 'sessions' in metrics else None})
        result.sort(key=lambda row: (-row['clicks'], -row['impressions'], row['page']))
        return {'rows': result[:limit], 'total': len(result), 'unavailable': False, 'diagnostics': self.diagnostics, 'notice': notice}

    def _organic_ga4(self, context, period, filters, dimensions=()):
        contract = analytics_contracts.GA4ReportContract('seo_organic_' + '_'.join(dimensions), 'Organic search', 'SEO', tuple(dimensions), ('sessions', 'engagedSessions', 'ecommercePurchases', 'purchaseRevenue'), 'session', (), 100000, 'property currency', filters=(('sessionDefaultChannelGroup', 'EXACT', 'Organic Search'),))
        extra = []
        market = filters.get('market', 'All markets')
        if market != 'All markets':
            extra.append(('countryId', 'EXACT', {'AU': 'AU', 'Australia': 'AU', 'US': 'US', 'United States': 'US', 'UK': 'GB', 'United Kingdom': 'GB'}[market]))
        if filters.get('device', 'All devices') != 'All devices':
            extra.append(('deviceCategory', 'EXACT', filters['device'].lower()))
        return self.reports.ga4(context['ga4_property_id'], contract, period['start_date'], period['end_date'], filters=extra)

    def cache_revision(self):
        return repr(self.reports.identity(self.reports.connection()))

    def source_health(self):
        context = self.reporting_context()
        health = self._health(context)
        health['ga4'] = {'available': bool(context.get('ga4_property_id')), 'identifier': context.get('ga4_property_id'), 'through_date': datetime.now(ZoneInfo('Australia/Sydney')).date().isoformat(), 'status': 'google_direct'}
        return health

    def snapshot(self, *, source_scope='seo', source_health=None, **filters):
        context = self.reporting_context()
        result = self.overview_base(filters, context=context)
        result['source_periods'] = {'gsc': result['period']}
        result['top_pages'] = self.landing_pages(filters, context=context)['rows']
        result['countries'], result['devices'] = [], []
        result['stale'], result['read_errors'] = False, {}
        return result

# Preserve the existing mixed-source SEO analysis contract. Only Google bundles
# change provider; the existing Shopify/confirmed-order readers remain untouched.
import seo_live_analytics as _live


class DirectSEOLiveReader(_live.PostgresSEOLiveAnalyticsReader):
    def __init__(self, phase4_store=None, reports=None):
        super().__init__(phase4_store)
        self.direct = DirectSEOReader(reports, phase4_store)

    def cache_revision(self):
        return self.direct.cache_revision()

    def source_health(self):
        health = self.direct.source_health()
        shopify = self._query_one('shopify', "SELECT MAX(COALESCE(processed_at, created_at)::date) AS through_date, COUNT(*) AS rows FROM shopify_orders WHERE cancelled_at IS NULL AND LOWER(COALESCE(financial_status, ''))='paid'")
        reconciled = self._query_one('reconciliation', 'SELECT MAX(date) AS through_date, COUNT(*) AS rows FROM seo_reporting_revenue_daily WHERE workspace_key=%s', (_live.WORKSPACE_KEY,))
        for source, row in (('shopify', shopify), ('reconciliation', reconciled)):
            health[source] = {'available': bool(row.get('rows')), 'through_date': str(row.get('through_date') or ''), 'status': 'saved', 'identifier': ''}
        return health

    def _gsc_bundle(self, health, period, market, device, compare):
        filters = {'market': market, 'device': device, 'search_type': self._active_search_type, 'query_class': self._active_query_class, 'brand_terms': self._brand_terms, 'preset': 'Today' if self._active_data_state == 'all' else 'Custom range', 'custom_start': period['start_date'], 'custom_end': period['end_date'], 'comparison': 'Previous period' if compare else 'Off'}
        context = {'available': True, 'status': 'google_direct', 'through_date': str(period['end_date']), 'gsc_site_url': health['identifier'], 'watermark': '', 'ga4_property_id': ''}
        rows = self.direct.reports.gsc(period['start_date'], period['end_date'], ('date',), filters)
        previous = self.direct.reports.gsc(period['previous_start_date'], period['previous_end_date'], ('date',), filters) if compare and period.get('previous_start_date') else []
        pages = self.direct.reports.gsc(period['start_date'], period['end_date'], ('page',), filters)
        old_pages = {row['page']: row for row in self.direct.reports.gsc(period['previous_start_date'], period['previous_end_date'], ('page',), filters)} if previous else {}
        breakdowns = self.direct.reports.gsc(period['start_date'], period['end_date'], ('country', 'device'), filters)
        # Pass the original period through, including previous-year comparisons.
        old_period = self.direct.period
        self.direct.period = lambda _filters, _context: period
        try:
            queries = self.direct._queries(filters, context)
        finally:
            self.direct.period = old_period
        return {'current': self.direct._totals(rows), 'previous': self.direct._totals(previous) if compare else {}, 'daily': [{'date': row['date'], **self.direct._totals([row])} for row in rows], 'previous_daily': [{'date': row['date'], **self.direct._totals([row])} for row in previous], 'top_queries': queries, 'top_pages': [{**row, 'page_url': row['page'], 'previous_clicks': old_pages.get(row['page'], {}).get('clicks', 0)} for row in pages], 'breakdowns': [{**row, 'country_code': row.get('country'), 'device': row.get('device')} for row in breakdowns]}

    def _ga4_bundle(self, health, period, market, device, compare):
        context = {'ga4_property_id': health['identifier']}
        filters = {'market': market, 'device': device}
        def fetch(dimensions, dates=period):
            report = self.direct._organic_ga4(context, dates, filters, dimensions)
            result = []
            for item in report['rows']:
                metrics, dims = item['metrics'], item['dimensions']
                day = dims.get('date', '')
                result.append({**dims, 'date': f'{day[:4]}-{day[4:6]}-{day[6:]}' if day else '', 'sessions': Decimal(metrics.get('sessions', 0)), 'engaged_sessions': Decimal(metrics.get('engagedSessions', 0)), 'transactions': Decimal(metrics.get('ecommercePurchases', 0)), 'purchase_revenue': Decimal(metrics.get('purchaseRevenue', 0)), 'property_currency': report['currency']})
            return result
        totals = fetch(())
        daily = fetch(('date',))
        pages = fetch(('landingPagePlusQueryString',))
        breakdowns = fetch(('countryId', 'deviceCategory'))
        old = {'start_date': period.get('previous_start_date'), 'end_date': period.get('previous_end_date')}
        previous = fetch((), old) if compare and old['start_date'] else []
        previous_daily = fetch(('date',), old) if previous else []
        previous_pages = {row['landingPagePlusQueryString']: row for row in fetch(('landingPagePlusQueryString',), old)} if previous else {}
        return {'current': self._aggregate_ga4(totals), 'previous': self._aggregate_ga4(previous) if compare else {}, 'daily': [{'date': row['date'], **self._aggregate_ga4([row])} for row in daily], 'previous_daily': [{'date': row['date'], **self._aggregate_ga4([row])} for row in previous_daily], 'top_pages': [{**row, 'landing_page_path_query': row['landingPagePlusQueryString'], 'attributed_purchases': row['transactions'], 'attributed_revenue': row['purchase_revenue'], 'currencies': [row['property_currency']], 'previous_sessions': previous_pages.get(row['landingPagePlusQueryString'], {}).get('sessions', 0)} for row in pages], 'breakdowns': [{**row, 'country_code': row.get('countryId'), 'device': row.get('deviceCategory')} for row in breakdowns]}
