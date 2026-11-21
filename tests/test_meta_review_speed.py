"""Bounded independent reads, complete snapshots and unchanged failure contracts."""
from copy import deepcopy
from threading import Event, Lock
import unittest
from unittest.mock import patch

import meta_ads_client as meta
import meta_review_live as live
from scripts.benchmark_meta_review_speed import CONFIG, SINCE, UNTIL, Fixture


class OverviewSpeedTests(unittest.TestCase):
    def tearDown(self):
        with live.retry._cooldown_lock:
            live.retry._cooldowns.pop(CONFIG['ad_account_id'], None)

    def test_reports_overlap_but_account_and_campaigns_are_validated_first(self):
        fixture = Fixture(delay=False)
        entered = {'totals': Event(), 'country': Event()}
        finished, guard = [], Lock()

        def response(path, params, config):
            if path.endswith('/insights'):
                kind = 'country' if params.get('breakdowns') else 'totals'
                other = 'totals' if kind == 'country' else 'country'
                entered[kind].set()
                self.assertTrue(entered[other].wait(2), 'Independent reads did not overlap')
                with guard:
                    self.assertEqual(finished, ['account', 'campaign1', 'campaign2'])
            else:
                with guard:
                    finished.append('account' if path == 'act_123' else 'campaign2' if params.get('after') else 'campaign1')
            return fixture.request(path, params, config)

        with patch.object(meta, '_request', side_effect=response), patch.object(meta, '_post') as write:
            result = live.load_overview(CONFIG, SINCE, UNTIL)
        self.assertEqual(len(result['campaigns']), 20)
        self.assertTrue(all(row['metrics']['roas'] == 3.25 for row in result['campaigns']))
        self.assertEqual(len(fixture.calls), 7)
        write.assert_not_called()

    def test_wrong_account_or_campaign_failure_never_starts_insights(self):
        for values in ([{'account_id': 'wrong'}],
                       [{'account_id': '123'}, meta.MetaAdsApiError('No permission', error_code=200)]):
            with self.subTest(values=values), patch.object(meta, '_request', side_effect=values) as request:
                with self.assertRaises((ValueError, meta.MetaAdsApiError)):
                    live.load_overview(CONFIG, SINCE, UNTIL)
                self.assertTrue(all(not c.args[0].endswith('/insights') for c in request.call_args_list))

    def test_failed_supplement_keeps_entire_previous_cached_snapshot(self):
        fixture = Fixture(delay=False)
        old = {'account': {'currency': 'AUD'}, 'campaigns': [{'campaign_id': 'old'}]}
        cache, key = {}, (live.scope(CONFIG), 'speed-test')
        live.cached_read(cache, key, lambda: deepcopy(old), clock=lambda: 1)

        def response(path, params, config):
            if params.get('breakdowns'):
                raise meta.MetaAdsApiError('No permission', error_code=200)
            return fixture.request(path, params, config)

        with patch.object(meta, '_request', side_effect=response):
            entry = live.cached_read(cache, key, lambda: live.load_overview(CONFIG, SINCE, UNTIL), clock=lambda: 200)
        self.assertEqual(entry['data'], old)
        self.assertTrue(entry['stale'])
        self.assertTrue(entry['error'])

    def test_primary_validation_error_still_precedes_supplement_error(self):
        fixture = Fixture(delay=False)

        def response(path, params, config):
            if params.get('breakdowns'):
                raise meta.MetaAdsApiError('No permission', error_code=200)
            if path.endswith('/insights'):
                return {'data': [{'spend': '1'}]}
            return fixture.request(path, params, config)

        with patch.object(meta, '_request', side_effect=response):
            with self.assertRaisesRegex(ValueError, 'without a campaign identity'):
                live.load_overview(CONFIG, SINCE, UNTIL)

    def test_rate_limit_is_shared_with_other_report_pages(self):
        fixture = Fixture(delay=False)
        limited = Event()
        seen = []

        def response(path, params, config):
            if path.endswith('/insights'):
                seen.append((bool(params.get('breakdowns')), params.get('after')))
                if params.get('breakdowns'):
                    limited.set()
                    raise meta.MetaAdsApiError('Rate limit', error_code=4, status_code=429, retry_after=120)
                self.assertTrue(limited.wait(2))
                # Wait until the worker has recorded the shared cooldown.
                for _ in range(1000):
                    if live.retry._cooldown_remaining(config['ad_account_id'], live.time.monotonic):
                        break
                    Event().wait(.001)
            return fixture.request(path, params, config)

        with patch.object(meta, '_request', side_effect=response):
            with self.assertRaises(live.retry.ReportingCooldown):
                live.load_overview(CONFIG, SINCE, UNTIL)
        self.assertFalse(any(after for _, after in seen))


if __name__ == '__main__':
    unittest.main()
