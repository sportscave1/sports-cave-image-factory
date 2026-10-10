"""Offline commercial arithmetic, privacy, scope and creative-contract regressions."""
from copy import deepcopy
from datetime import date
import json
import unittest
from unittest.mock import patch

import design_studio_sales_intelligence as intel
import design_studio_intelligence_store as store
import design_studio_styles as styles
import sports_cave_dashboard as dashboard


def fixture_sources():
    products = [
        {'id': 'gid://shopify/Product/1', 'title': 'The Baseball Memory', 'handle': 'baseball-memory',
         'tags': ['MLB'], 'published_at': '2026-01-01', 'synced_at': '2026-10-09T20:00:00Z',
         'image_url': 'https://cdn.shopify.com/s/files/baseball.jpg?v=1', 'design_style': 'ultimate_moment'},
        {'id': '2', 'title': 'The Catch', 'handle': 'the-catch', 'tags': ['NFL'], 'published_at': '2026-09-01'},
        {'id': '3', 'title': 'Baseball Newcomer', 'handle': 'newcomer', 'tags': ['Baseball'], 'published_at': '2026-10-01'},
        {'id': '4', 'title': 'Track Champion', 'handle': 'track', 'tags': ['Formula One']},
    ]
    def line(oid, pid, qty, when, **extra):
        return {'order_id': str(oid), 'line_id': str(oid), 'product_id': str(pid), 'quantity': qty,
                'financial_status': 'PAID', 'test': False, 'created_at': when,
                'currency': 'AUD', 'market': 'AU', 'price': '100', 'discount': '10',
                'refunds_known': True, 'refunds': [], 'synced_at': '2026-10-09T20:00:00Z',
                'customer_email': 'private@example.com', 'customer_name': 'Private Customer', **extra}
    lines = [line(1, 1, 5, '2026-01-05'), line(2, 1, 3, '2026-09-04',
             financial_status='PARTIALLY_REFUNDED', refunds=[{'quantity': 1, 'subtotal': '90'}]),
             line(3, 2, 2, '2026-09-10'), line(4, 3, 3, '2026-10-02'),
             line(5, 1, 30, '2026-09-10', test=True), line(6, 1, 40, '2026-09-10', cancelled_at='2026-09-11'),
             line(7, 1, 50, '2026-09-10', financial_status='PENDING'),
             line(8, 1, 60, '2026-09-10', test=None), line(9, 1, 100, '2025-09-01')]
    lines.append(deepcopy(lines[0]))
    return {'products': products, 'lines': lines,
            'meta': [{'product_handle': 'baseball-memory', 'spend': 400, 'currency': 'AUD', 'impressions': 10000,
                      'clicks': 200, 'attributed_purchases': 6, 'attributed_value': 600}],
            'ga4': [{'path': '/products/baseball-memory?utm_source=x', 'sessions': 100,
                     'country': 'AU', 'device': 'mobile', 'channel': 'Organic Search', 'thresholded': True}],
            'tracking': [{'product_id': '1', 'date_created': '2026-01-01', 'first_order': '', 'designed_by': 'Private Staff'}]}


def snapshot(sport='Baseball', market='All', sources=None):
    start, end = intel.reporting_window(date(2026, 10, 10))
    return intel.scope_snapshot(intel.aggregate_sources(sources or fixture_sources(), start, end), sport, market)


class CommercialEvidenceTests(unittest.TestCase):
    def setUp(self):
        intel._CACHE.clear()

    def test_refunds_cancellations_duplicates_and_units_vs_orders(self):
        row = next(r for r in snapshot()['performers'] if r['product_id'] == '1')
        self.assertEqual((row['gross_units'], row['orders'], row['net_units']), (8, 2, 7))
        self.assertEqual((row['gross_sales'], row['discounts'], row['refunds'], row['net_revenue']), (800, 20, 90, 690))
        self.assertEqual(row['monthly_gross_units'], {'2026-01': 5, '2026-09': 3})
        self.assertEqual(row['recent_30d_gross_units'], 0)
        self.assertEqual(row['prior_30d_gross_units'], 3)

    def test_raw_and_normalised_rankings_are_separate(self):
        snap = snapshot()
        self.assertTrue(snap['raw_units_ranking'][0].startswith('1 /'))
        self.assertTrue(snap['velocity_ranking'][0].startswith('3 /'))
        row = next(r for r in snap['performers'] if r['product_id'] == '3')
        self.assertEqual(row['days_observed'], 9)
        self.assertEqual(row['gross_units_per_30_observed_days'], 10)

    def test_missing_refunds_or_finance_never_becomes_zero(self):
        for field, value in [('refunds_known', False), ('price', None), ('discount', None), ('unallocated_refund', True)]:
            data = fixture_sources()
            data['lines'][0][field] = value
            snap = snapshot(sources=data)
            row = next(r for r in snap['performers'] if r['product_id'] == '1')
            self.assertIsNone(row['net_revenue'])
            self.assertNotIn('1 / AU / AUD', snap['net_revenue_rankings_by_currency']['AUD'])

    def test_discount_allocations_not_double_counted(self):
        data = fixture_sources()
        data['lines'][0]['discount_allocations'] = [{'amount': '7'}, {'amount': '8'}]
        row = next(r for r in snapshot(sources=data)['performers'] if r['product_id'] == '1')
        self.assertEqual(row['discounts'], 25)

    def test_invalid_refund_and_nonfinite_money_suppress_net(self):
        for change in ({'price': 'NaN'}, {'refunds': [{'quantity': 99, 'subtotal': '900'}]}):
            data = fixture_sources()
            data['lines'][0].update(change)
            row = next(r for r in snapshot(sources=data)['performers'] if r['product_id'] == '1')
            self.assertIsNone(row['net_revenue'])

    def test_markets_currencies_and_sports_never_blended(self):
        data = fixture_sources()
        extra = deepcopy(data['lines'][0])
        extra.update(order_id='100', line_id='100', market='US', currency='USD')
        data['lines'].append(extra)
        au = snapshot('MLB', 'AU', data)
        self.assertEqual({r['market'] for r in au['performers']}, {'AU'})
        self.assertEqual({r['sport'] for r in au['performers']}, {'Baseball'})
        self.assertEqual(set(snapshot(sources=data)['net_revenue_rankings_by_currency']), {'AUD', 'USD'})
        self.assertEqual(snapshot('NFL')['products_analysed'], 1)
        self.assertEqual(snapshot('Golf')['products_analysed'], 0)
        self.assertIn('comparable motorsport', snapshot('NASCAR')['scope'])

    def test_calendar_year_and_leap_day(self):
        start, end = intel.reporting_window(date(2024, 2, 29))
        self.assertEqual(str(start.date()), '2023-02-28')
        self.assertEqual(str(end.date()), '2024-02-29')
        self.assertEqual(str(start.tzinfo), 'Australia/Sydney')

    def test_unknown_or_invalid_publication_is_labelled_observed(self):
        for publication in (None, '2027-01-01'):
            data = fixture_sources()
            data['products'][0]['published_at'] = publication
            row = next(r for r in snapshot(sources=data)['performers'] if r['product_id'] == '1')
            self.assertIn('first observed sale', row['availability_basis'])

    def test_meta_never_inflates_shopify_and_ga4_gaps_are_explicit(self):
        snap = snapshot()
        row = next(r for r in snap['performers'] if r['product_id'] == '1')
        self.assertEqual(row['net_revenue'], 690)
        self.assertEqual(row['meta'][0]['reported_roas'], 1.5)
        self.assertEqual(row['ga4'][0]['channel'], 'Organic Search')
        self.assertTrue(any('no matched' in x for x in snapshot('NFL')['limitations']))

    def test_product_identity_and_no_fabricated_dna(self):
        dna = next(r for r in snapshot()['performers'] if r['product_id'] == '1')['winning_design_dna']
        self.assertEqual(dna['product_id'], '1')
        self.assertEqual(dna['image_url'], 'https://cdn.shopify.com/s/files/baseball.jpg')
        self.assertFalse(dna['pixels_inspected'])
        self.assertEqual(dna['observations'], {})
        self.assertEqual(intel.winning_design_dna({'id': '9', 'image_url': 'http://127.0.0.1/secret'})['image_url'], '')

    def test_customer_and_staff_details_cannot_enter_snapshot_or_prompt(self):
        data = fixture_sources()
        data['tracking'][0]['first_order'] = 'private@example.com'
        text = intel.intelligence_context(snapshot(sources=data))
        for secret in ('private@example.com', 'Private Customer', 'Private Staff', 'customer_email', 'designed_by'):
            self.assertNotIn(secret, text)

    def test_stale_source_is_explicitly_not_current(self):
        data = fixture_sources()
        for line in data['lines']:
            line['synced_at'] = '2026-01-01'
        self.assertIn('stale or unknown', snapshot(sources=data)['performers'][0]['source_freshness'])

    def test_shared_cache_reuses_aggregate_across_sports_and_refreshes(self):
        with patch.object(store, 'load_sources', return_value=fixture_sources()) as load:
            intel.get_snapshot('Baseball')
            intel.get_snapshot('NFL')
            self.assertEqual(load.call_count, 1)
            intel.get_snapshot('Baseball', refresh=True)
            self.assertEqual(load.call_count, 2)
        self.assertNotIn('private@example.com', repr(intel._CACHE))

    def test_outage_does_not_reuse_old_snapshot_or_expose_diagnostics(self):
        with patch.object(store, 'load_sources', side_effect=[fixture_sources(), RuntimeError('secret token')]):
            self.assertTrue(intel.get_snapshot('Baseball')['performers'])
            failed = intel.get_snapshot('Baseball', refresh=True)
            self.assertEqual(failed['performers'], [])
            self.assertNotIn('secret token', json.dumps(failed))

    def test_expired_snapshot_is_reloaded(self):
        with patch.object(store, 'load_sources', return_value=fixture_sources()) as load, patch.object(intel.clock, 'monotonic', side_effect=[0, 1801, 1801]):
            intel.get_snapshot('Baseball')
            intel.get_snapshot('Baseball')
            self.assertEqual(load.call_count, 2)

    def test_style_mix_fallback_is_exact_and_does_not_mutate(self):
        base = dashboard.suggest_design_idea_style_mix('Baseball', 10)
        original = dict(base)
        result, reason = intel.suggest_evidence_mix(base, snapshot())
        self.assertEqual(result, original)
        self.assertEqual(base, original)
        self.assertIn('insufficient', reason)

    def test_supported_style_suggestion_is_bounded(self):
        rows = [dict(product_id=str(i), design_style=s, net_units=n, orders=10, days_observed=100)
                for i, s, n in [(1, 'a', 30), (2, 'a', 30), (3, 'b', 10), (4, 'b', 10)]]
        result, _ = intel.suggest_evidence_mix({'a': 4, 'b': 4, 'unselected': 0}, {'performers': rows})
        self.assertEqual(result, {'a': 5, 'b': 3, 'unselected': 0})

    def test_original_style_prompts_are_exact_suffix_and_handoffs_unchanged(self):
        for style in styles.style_slugs():
            details = {'sport': 'NFL', 'principal_subject_one': 'Joe Montana', 'event_moment': 'The Catch'}
            bundle = styles.build_prompt_bundle(style, 'Locked task', details, [])
            before = deepcopy(bundle)
            bundle['research'] = intel.prepend_context(bundle['research'], snapshot('NFL'))
            self.assertTrue(bundle['research'].endswith(before['research']))
            self.assertIn('Moment Lock', bundle['research'])
            self.assertEqual({k: v for k, v in bundle.items() if k != 'research'}, {k: v for k, v in before.items() if k != 'research'})

    def test_ideas_keep_csv_row_style_and_duplicate_contracts_without_io(self):
        mix = dashboard.suggest_design_idea_style_mix('Baseball', 7)
        with patch.object(store, 'load_sources', side_effect=AssertionError('Builder must be pure')):
            prompt = dashboard.build_new_design_ideas_prompt('Baseball', 7, mix, intelligence_snapshot=snapshot())
        self.assertIn(','.join(dashboard.TASK_IMPORT_CSV_COLUMNS), prompt)
        self.assertIn('exactly 7 new Baseball', prompt)
        self.assertIn('The Baseball Memory', prompt)
        self.assertIn('690.0', prompt)
        self.assertIn('The same athlete with substantially the same story', prompt)
        self.assertIn('no extra commentary or columns', prompt)
        self.assertEqual(sum(mix.values()), 7)

    def test_fallback_ideas_still_generate(self):
        mix = dashboard.suggest_design_idea_style_mix('NFL', 4)
        prompt = dashboard.build_new_design_ideas_prompt('NFL', 4, mix)
        self.assertIn('Historical sales evidence is unavailable', prompt)
        self.assertIn('exactly 4', prompt)


class ReadOnlyStoreTests(unittest.TestCase):
    def test_allowlisted_sql_has_no_customer_columns_or_mutations(self):
        for name in ('PRODUCTS_SQL', 'LINES_SQL', 'META_SQL', 'GA4_SQL', 'TRACKING_SQL'):
            sql = getattr(store, name)
            self.assertNotRegex(sql.upper(), r'\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b')
            self.assertNotIn('customer', sql.lower())
            self.assertNotIn('SELECT *', sql)

    def test_source_failure_is_isolated_and_selects_are_read_only(self):
        from unittest.mock import MagicMock
        cur = MagicMock()
        cur.fetchall.side_effect = [[{'id': '1'}], RuntimeError('secret'), [], [], []]
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cur
        result = store.load_sources(*intel.reporting_window(date(2026, 10, 10)), connect=lambda: conn)
        self.assertEqual(result['products'], [{'id': '1'}])
        self.assertEqual(result['lines'], [])
        statements = [call.args[0] for call in cur.execute.call_args_list]
        self.assertEqual(statements[0], 'SET TRANSACTION READ ONLY')
        self.assertIn('ROLLBACK TO SAVEPOINT intelligence_source', statements)
        self.assertNotIn('secret', repr(result))
        conn.commit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
