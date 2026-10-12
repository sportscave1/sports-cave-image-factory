"""Offline direct-report contracts. Network and production stores are never used."""
from datetime import date, datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import ast
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch

import google_direct_reporting as direct
import analytics_contracts
import analytics_reporting
import google_seo_import
import google_seo_phase4


class MemoryTests(unittest.TestCase):
    def test_expiry_single_flight_and_defensive_copy(self):
        now = [0]
        cache = direct.MemoryReports(clock=lambda: now[0])
        calls = []
        def fetch():
            calls.append(1)
            time.sleep(.01)
            return {'rows': [1]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: cache.read('same', 20, fetch), range(4)))
        self.assertEqual(len(calls), 1)
        values[0]['rows'].append(2)
        self.assertEqual(cache.read('same', 20, fetch), {'rows': [1]})
        now[0] = 20
        cache.read('same', 20, fetch)
        self.assertEqual(len(calls), 2)

    def test_capacity_and_failure_not_cached(self):
        cache = direct.MemoryReports(max_bytes=100)
        for i in range(50):
            cache.read(i, 100, lambda: 'x' * 20)
        self.assertLessEqual(cache.size, 100)
        failure = Mock(side_effect=ValueError('failed'))
        for _ in range(2):
            with self.assertRaises(ValueError):
                cache.read('bad', 100, failure)
        self.assertEqual(failure.call_count, 2)

    def test_refresh_keeps_quota_cooldown(self):
        cache = direct.MemoryReports()
        cache.cooldowns['scope'] = 100
        cache.clear()
        self.assertEqual(cache.cooldowns['scope'], 100)


class TransportTests(unittest.TestCase):
    def test_429_does_not_retry_and_blocks_other_contracts(self):
        cache = direct.MemoryReports(clock=lambda: 100)
        client = direct.DirectTransport('fake-token', 'property', cache=cache)
        client.request_post = Mock(return_value=Mock(status_code=429, headers={'Retry-After': '120'}))
        for endpoint in ('one', 'two'):
            with self.assertRaises(direct.DirectReportingError):
                client._post(endpoint, {}, stage='test')
        self.assertEqual(client.request_post.call_count, 1)
        self.assertEqual(cache.cooldowns['property'], 220)

    def test_low_ga4_quota_blocks_following_requests(self):
        cache = direct.MemoryReports(clock=lambda: 100)
        client = direct.DirectTransport('fake', 'p', cache=cache)
        response = Mock(status_code=200)
        response.json.return_value = {'propertyQuota': {'tokensPerHour': {'remaining': 2}}}
        client.request_post = Mock(return_value=response)
        client._post('one', {}, stage='test')
        with self.assertRaises(direct.DirectReportingError):
            client._post('two', {}, stage='test')
        self.assertEqual(client.request_post.call_count, 1)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.connection = {'id': 'c', 'gsc_site_url': 'sc-domain:example.test', 'ga4_property_id': 'properties/1', 'updated_at': '2026-10-01T00:00:00Z'}
        self.store = Mock()
        self.store.get_connection.return_value = self.connection
        self.client = Mock()
        self.client._gsc_endpoint.return_value = 'https://example.invalid/query'
        self.reports = direct.GoogleReports(connection_store=self.store, cache=direct.MemoryReports(), client_factory=lambda _: self.client)
        self.today = datetime.now().date()

    def test_gsc_country_device_brand_and_weighting(self):
        self.client._post.return_value = {'rows': [{'keys': ['test'], 'clicks': 3, 'impressions': 10, 'position': 4.5, 'ctr': .3}]}
        rows = self.reports.gsc(self.today, self.today, ('query',), {'market': 'AU', 'device': 'Mobile', 'query_class': 'Branded', 'brand_terms': ['a.b'], 'search_type': 'image'})
        payload = self.client._post.call_args.args[1]
        self.assertEqual(payload['type'], 'image')
        self.assertEqual(payload['aggregationType'], 'byProperty')
        self.assertEqual([c['expression'] for c in payload['dimensionFilterGroups'][0]['filters']], ['aus', 'mobile', '(?i)(a\\.b)'])
        self.assertEqual(rows[0]['position_weight'], Decimal('45.0'))
        self.reports.gsc(self.today, self.today, ('query',), {'market': 'AU', 'device': 'Mobile', 'query_class': 'Branded', 'brand_terms': ['a.b'], 'search_type': 'image'})
        self.assertEqual(self.client._post.call_count, 1)
        self.store.get_connection_secret.assert_not_called()

    def test_pagination_offsets_and_exhaustion(self):
        one = {'keys': ['one'], 'clicks': 1, 'impressions': 2, 'position': 3}
        two = {**one, 'keys': ['two']}
        self.client._post.side_effect = [{'rows': [one, two]}, {'rows': []}]
        with patch.object(direct, 'GSC_PAGE_SIZE', 2):
            rows = self.reports.gsc(self.today, self.today, ('query',), {})
        self.assertEqual(len(rows), 2)
        self.assertEqual([c.args[1]['startRow'] for c in self.client._post.call_args_list], [0, 2])

    def test_repeated_page_fails_without_caching_partial_result(self):
        row = {'keys': ['one'], 'clicks': 1, 'impressions': 2, 'position': 3}
        self.client._post.return_value = {'rows': [row]}
        with patch.object(direct, 'GSC_PAGE_SIZE', 1):
            with self.assertRaises(direct.DirectReportingError) as raised:
                self.reports.gsc(self.today, self.today, ('query',), {})
        self.assertEqual(raised.exception.code, 'gsc_pagination_repeated')
        self.assertEqual(self.reports.cache.size, 0)

    def test_page_filter_requires_page_aggregation(self):
        self.client._post.return_value = {'rows': []}
        self.reports.gsc(self.today, self.today, (), {'extra_filters': [{'dimension': 'page', 'operator': 'equals', 'expression': 'https://example.test/'}]})
        self.assertEqual(self.client._post.call_args.args[1]['aggregationType'], 'auto')

    def test_unavailable_history_never_calls_google(self):
        with self.assertRaises(direct.DirectReportingError) as raised:
            self.reports.gsc(date(2020,1,1), date(2020,1,2), (), {})
        self.assertEqual(raised.exception.code, 'gsc_history_unavailable')
        self.client._post.assert_not_called()

    def test_property_switch_cannot_reuse_cache(self):
        self.client._post.return_value = {'rows': []}
        self.reports.gsc(self.today, self.today, (), {})
        self.connection['gsc_site_url'] = 'sc-domain:other.test'
        self.reports.gsc(self.today, self.today, (), {})
        self.assertEqual(self.client._post.call_count, 2)

    def test_oauth_secret_projection_reuses_existing_connection(self):
        secret = {'gsc_site_url': self.connection['gsc_site_url'], 'ga4_property_id': self.connection['ga4_property_id']}
        reports = direct.GoogleReports(connection_store=self.store, cache=direct.MemoryReports())
        with patch.object(direct.google_seo, 'load_config', return_value={}), patch.object(direct.google_seo, 'access_token_for_connection', return_value=('fake', secret)) as refresh:
            self.assertEqual(reports.client(self.connection).access_token, 'fake')
            self.assertEqual(reports.client(self.connection).access_token, 'fake')
        self.assertEqual(refresh.call_count, 1)

    def test_realtime_uses_only_supported_request_fields(self):
        self.client._post.return_value = {'rows': [], 'rowCount': 0}
        client = analytics_reporting.CanonicalGA4Client('', reporting_client=self.client)
        client.fetch_report('properties/1', 'realtime', self.today, self.today)
        request = self.client._post.call_args.args[1]
        self.assertNotIn('offset', request)
        self.assertNotIn('keepEmptyRows', request)
        self.assertNotIn('dateRanges', request)
        self.assertEqual(self.client._post.call_count, 1)

    def test_ga4_exact_contract_and_no_persistence(self):
        report = {'rows': [], 'metadata': {}, 'quality': {'status': 'GA4 verified'}, 'complete': True}
        with patch.object(analytics_reporting.CanonicalGA4Client, 'fetch_report', return_value=report) as fetch:
            result = self.reports.ga4('properties/1', 'overview_totals', self.today, self.today)
            self.reports.ga4('properties/1', 'overview_totals', self.today, self.today)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result['quality_status'], 'GA4 verified')
        self.assertEqual(fetch.call_args.args[1], analytics_contracts.report_contract('overview_totals'))


class SEOTests(unittest.TestCase):
    def setUp(self):
        self.reports = Mock()
        settings = Mock()
        settings.get_settings.return_value = {'brand_terms': ['sports cave']}
        self.reader = direct.DirectSEOReader(self.reports, settings)
        self.context = {'available': True, 'status': 'google_direct', 'through_date': '2026-10-10', 'gsc_site_url': 'sc-domain:example.test', 'watermark': 'v1'}
        self.filters = {'preset': 'Last 7 days', 'comparison': 'Previous period'}
        def response(start, end, dimensions, filters):
            previous = str(end) < '2026-10-04'
            if dimensions == ('date',):
                return [{'date': str(end), 'clicks': Decimal(20 if previous else 30), 'impressions': Decimal(100), 'position_weight': Decimal(500)}]
            return [{'query': q, 'clicks': Decimal(2 if previous else 3), 'impressions': Decimal(10), 'position_weight': Decimal(60 if previous else 50), 'average_position': Decimal(6 if previous else 5), 'ctr': Decimal('.3')} for q in ('a', 'b', 'c')]
        self.reports.gsc.side_effect = response

    def test_totals_are_not_sum_of_visible_queries(self):
        result = self.reader.overview_base(self.filters, context=self.context)
        self.assertEqual(result['current']['organic_clicks'], 30)
        self.assertEqual(result['known_query_clicks'], 9)
        self.assertEqual(result['current']['ctr'], Decimal('.3'))
        self.assertEqual(result['previous']['organic_clicks'], 20)

    def test_supporting_ga4_failure_keeps_gsc_landing_pages(self):
        self.context['ga4_property_id'] = 'properties/1'
        self.reports.gsc.return_value = [{'page': 'https://example.test/products/a', 'clicks': Decimal(3), 'impressions': Decimal(10), 'position_weight': Decimal(50), 'average_position': Decimal(5)}]
        self.reports.gsc.side_effect = None
        with patch.object(direct._live.PostgresSEOLiveAnalyticsReader, '_canonical_metadata', return_value={}), patch.object(self.reader, '_organic_ga4', side_effect=direct.DirectReportingError('quota')):
            result = self.reader.landing_pages(self.filters, context=self.context)
        self.assertEqual(result['rows'][0]['clicks'], 3)
        self.assertIsNone(result['rows'][0]['sessions'])
        self.assertIn('unavailable', result['notice'])

    def test_mapped_queries_remain_visible_outside_unmapped_view(self):
        rows = self.reader.query_page(self.filters, context=self.context, view='All', excluded_queries=('b',))['rows']
        self.assertEqual({row['query'] for row in rows}, {'a', 'b', 'c'})

    def test_query_cursor_stable_and_dismissals_preserved(self):
        first = self.reader.query_page(self.filters, context=self.context, limit=1, view='Opportunities', excluded_queries=('b',))
        second = self.reader.query_page(self.filters, context=self.context, limit=1, view='Opportunities', excluded_queries=('b',), cursor=first['next_cursor'])
        self.assertEqual([first['rows'][0]['query'], second['rows'][0]['query']], ['a', 'c'])
        self.assertIsNone(second['next_cursor'])
        self.assertEqual(first['total'], 2)


class RetiredJobsTests(unittest.TestCase):
    def test_imports_repairs_and_snapshot_writers_do_not_access_stores(self):
        store = Mock()
        self.assertEqual(google_seo_import.queue_daily_runs(import_store=store), [])
        self.assertEqual(google_seo_import.SEOImportWorker(import_store=store).run_once(), None)
        self.assertIsNone(google_seo_phase4.process_queued_reporting_repair(phase4_store=store))
        self.assertEqual(analytics_reporting.refresh_saved_report_contracts(store=store)['status'], 'disabled')
        self.assertEqual(store.mock_calls, [])
        backend = Mock()
        self.assertEqual(google_seo_phase4.PostgresSEOPhase4Store(backend).refresh_reporting_snapshots()['status'], 'disabled')
        self.assertEqual(backend.mock_calls, [])

    def test_startup_does_not_enqueue_repairs_or_call_google(self):
        tree = ast.parse(Path('sports_cave_server.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare_google_seo_storage')
        calls = [ast.unparse(n.func) for n in ast.walk(function) if isinstance(n, ast.Call)]
        self.assertEqual(calls, ['run_migrations.get_database_url', 'run_migrations.run_migrations'])


if __name__ == '__main__':
    unittest.main()
