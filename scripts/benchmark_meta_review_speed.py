"""Repeatable synthetic Meta overview benchmark; never uses provider credentials.

Supply the previous Git object's meta_review_live.py via --baseline. Delays model
independent provider reads, not measured production latency. Results include exact
response/request parity, cold/refresh timings and Streamlit control/table parity.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
from threading import Lock
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import meta_ads_client as meta
import meta_review_live as live

CONFIG = {'configured': True, 'ad_account_id': 'act_123',
          'api_version': 'v26.0', 'access_token': 'synthetic-only'}
SINCE, UNTIL = date(2026, 11, 1), date(2026, 11, 20)


class Fixture:
    def __init__(self, delay=True):
        self.delay, self.calls, self.lock = delay, [], Lock()

    def request(self, path, params, config):
        assert config == CONFIG, 'Only the synthetic account is permitted'
        with self.lock:
            self.calls.append(json.dumps([path, params], sort_keys=True))
        country = params.get('breakdowns') == 'country'
        if self.delay:
            time.sleep(.02 if path == 'act_123' or path.endswith('/campaigns') else .12 if country else .16)
        if path == 'act_123':
            return {'account_id': '123', 'name': 'Synthetic account', 'currency': 'AUD',
                    'timezone_name': 'Australia/Sydney'}
        ids = range(100, 110) if not params.get('after') else range(110, 120)
        if path.endswith('/campaigns'):
            rows = [{'id': str(i), 'name': 'Synthetic campaign ' + str(i),
                     'status': ('ACTIVE', 'PAUSED', 'ARCHIVED')[i % 3],
                     'effective_status': ('ACTIVE', 'PAUSED', 'ARCHIVED')[i % 3],
                     'created_time': '2026-11-01T00:00:00+1100'} for i in ids]
        elif path.endswith('/insights') and country:
            rows = [{'campaign_id': str(i), 'country': 'AU', 'spend': '25'} for i in ids]
        elif path.endswith('/insights'):
            rows = [{'campaign_id': str(i), 'spend': '25', 'impressions': '1000',
                     'reach': '900', 'clicks': '40', 'inline_link_clicks': '25',
                     'actions': [{'action_type': 'offsite_conversion.fb_pixel_purchase', 'value': '2'}],
                     'purchase_roas': [{'action_type': 'purchase', 'value': '3.25'}]}
                    for i in ids]
        else:
            raise AssertionError('Unexpected provider path: ' + path)
        result = {'data': rows}
        if not params.get('after'):
            result['paging'] = {'next': 'https://never-follow.invalid', 'cursors': {'after': 'page2'}}
        return result


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 11, 21, 2, 0, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def baseline_module(path):
    spec = importlib.util.spec_from_file_location('meta_review_baseline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def page_snapshot(app):
    assert not app.exception and not app.error
    return {
        'tables': [df.value.to_json(orient='split', date_format='iso') for df in app.dataframe],
        'buttons': [(b.label, b.disabled) for b in app.button],
        'inputs': [(i.label, i.value) for i in app.text_input],
        'selects': [(i.label, i.options, i.value) for i in app.selectbox],
        'dates': [(i.label, str(i.value)) for i in app.date_input],
        'captions': [c.value for c in app.caption],
    }


def measure(module, count=9):
    samples, results, calls = [], [], []
    for _ in range(count):
        fixture = Fixture()
        with patch.object(meta, '_request', side_effect=fixture.request), \
             patch.object(meta, '_post', side_effect=AssertionError('Provider write forbidden')):
            started = time.perf_counter()
            result = module.load_overview(CONFIG, SINCE, UNTIL)
            samples.append(round((time.perf_counter() - started) * 1000, 3))
        results.append(fingerprint(result))
        calls.append(sorted(Counter(fixture.calls).items()))
    assert len(set(results)) == 1 and all(c == calls[0] for c in calls)
    return {'samples_ms': samples, 'median_ms': statistics.median(samples),
            'response_sha256': results[0], 'request_multiset': calls[0],
            'request_count': sum(n for _, n in calls[0])}


def workflow(module):
    from streamlit.testing.v1 import AppTest
    import ads_meta_review_page as page
    fixture = Fixture()
    with patch.object(page, 'live', module), patch.object(meta, 'get_meta_config', return_value=CONFIG), \
         patch.object(meta, '_request', side_effect=fixture.request), \
         patch.object(meta, '_post', side_effect=AssertionError('Provider write forbidden')), \
         patch.object(page.recency, 'load', return_value={'available': False}), \
         patch.object(page, 'datetime', FixedDateTime), patch.object(module, 'datetime', FixedDateTime):
        app = AppTest.from_string('import ads_meta_review_page as p\np.render_page()', default_timeout=15)
        app.run()  # Warm Python/framework imports identically before measuring.
        samples, snapshots = [], []
        for _ in range(5):
            started = time.perf_counter()
            next(b for b in app.button if b.label == 'Refresh From Meta').click().run()
            samples.append(round((time.perf_counter() - started) * 1000, 3))
            snapshots.append(page_snapshot(app))
        # Existing read-only search, status and sort controls must retain results.
        checks = {'refresh': snapshots[-1]}
        app.text_input[0].input('Synthetic campaign 11').run()
        checks['search'] = page_snapshot(app)
        app.text_input[0].input('').run()
        app.selectbox[0].select('Spend').run()
        checks['sort'] = page_snapshot(app)
        assert all(s == snapshots[0] for s in snapshots)
        return {'samples_ms': samples, 'median_ms': statistics.median(samples),
                'screen_sha256': fingerprint(checks), 'campaign_count': 20}


def run(baseline):
    previous = baseline_module(baseline)
    before, after = measure(previous), measure(live)
    assert before['response_sha256'] == after['response_sha256']
    assert before['request_multiset'] == after['request_multiset']
    old_ui, new_ui = workflow(previous), workflow(live)
    assert old_ui['screen_sha256'] == new_ui['screen_sha256']
    assert after['median_ms'] < before['median_ms'] * .9
    return {'environment': 'isolated synthetic provider delays; not production speed',
            'baseline': before, 'candidate': after, 'baseline_workflow': old_ui,
            'candidate_workflow': new_ui, 'behaviour_preserved': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    print('META_SPEED_RESULT=' + json.dumps(run(args.baseline)))
