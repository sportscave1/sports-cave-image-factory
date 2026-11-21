import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock
import pytest
import home_seo_report as seo
import daily_brief_worker as worker
import os_accounts
import supabase_backend as db
from tests.test_auto_editions_jobs import database  # noqa: F401

TODAY = date(2026, 11, 21)
OWNER = {'id': 'seo-owner', 'email': 'owner@example.test', 'role': 'admin', 'session_version': 1}


def edition():
    return dict(date=str(TODAY), period_start='2026-10-22', period_end='2026-11-18',
                summary='Review the collector collection.', source_gaps=['Merchant Center not verified.'],
                next_action='Companion: inspect the existing page and prepare an exact proposed edit for review.',
                opportunities=[dict(query='sports wall art', market='AU', url='https://www.sportscaveshop.com/collections/sports',
                    evidence='Synthetic final GSC query/page evidence; availability still needs verification.',
                    availability='Not verified', action='Inspect buyer intent before changing copy.')])


@pytest.mark.parametrize('change', [
    {'date': '2026-11-20'}, {'period_end': '2026-11-21'}, {'period_start': '2026-11-01'},
    {'summary': ''}, {'source_gaps': 'unknown'}, {'opportunities': [{}]},
])
def test_rejects_invalid_report(change):
    with pytest.raises((ValueError, TypeError)):
        seo.parse(json.dumps({**edition(), **change}), TODAY)


@pytest.mark.parametrize('url', ['https://evil.example/collections/a', 'javascript:alert(1)',
                               'https://sportscaveshop.com@evil.example/', 'https://sportscaveshop.com:444/'])
def test_targets_stay_on_public_storefront(url):
    value = edition()
    value['opportunities'][0]['url'] = url
    with pytest.raises(ValueError):
        seo.parse(json.dumps(value), TODAY)


def test_gap_report_and_html_escape():
    value = {**edition(), 'opportunities': [], 'summary': '<script>unsafe</script>'}
    parsed = seo.parse(json.dumps(value), TODAY)
    markup = seo.compact_html(parsed, TODAY + timedelta(days=1))
    assert '<script>' not in markup and '&lt;script&gt;' in markup
    assert 'awaiting today' in markup


@pytest.fixture
def storage(database, monkeypatch):
    jobs, sql = database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz)')
    for module in (db, worker):
        monkeypatch.setattr(module, 'connect', jobs.connect)
    monkeypatch.setattr('sports_sales_calendar.sydney_date', lambda: TODAY)
    monkeypatch.setattr(worker, 'sydney_date', lambda: TODAY)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda _: OWNER)
    monkeypatch.setattr(os_accounts, 'is_reporting_owner', lambda u: u == OWNER)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *_: True)
    monkeypatch.setattr(os_accounts, 'can_access_reporting', lambda *_: True)
    return sql


def test_hosted_publication_archive_idempotency_and_readback(storage):
    worker.enqueue('seo', edition(), {'sub': 'seo-owner', 'version': '1'})
    assert worker.process_one()
    status = worker.status('seo')
    assert status['verified'] and status['matches_submission']
    saved = seo.latest()
    assert saved['published_at']
    assert db.get_app_setting(seo.HISTORY + str(TODAY), ensure_schema_first=False) == saved
    seo.publish(json.dumps(edition()), OWNER)
    with pytest.raises(ValueError, match='different SEO edition'):
        seo.publish(json.dumps({**edition(), 'summary': 'Different.'}), OWNER)
    assert seo.latest() == saved


def test_missing_publication_is_retryable(storage, monkeypatch):
    parse, publish, limit = worker.BRIEFS['seo']
    monkeypatch.setitem(worker.BRIEFS, 'seo', (parse, Mock(return_value=edition()), limit))
    worker.enqueue('seo', edition(), {'sub': 'seo-owner', 'version': '1'})
    assert worker.process_one()
    assert not worker.status('seo')['verified']
    monkeypatch.setitem(worker.BRIEFS, 'seo', (parse, publish, limit))
    storage.execute("UPDATE app_settings SET updated_at=now()-interval '3 minutes'")
    assert worker.process_one()
    assert worker.status('seo')['verified']


def test_seo_access_rechecked_before_queue(storage, monkeypatch):
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *_: False)
    with pytest.raises(PermissionError):
        worker.enqueue('seo', edition(), {'sub': 'seo-owner', 'version': '1'})


def test_context_is_bounded_serializable_and_market_filtered(monkeypatch):
    import seo_daily_context as context
    report = Mock()
    report.for_request.return_value = report
    report.gsc.return_value = [dict(query='sports art', page='https://www.sportscaveshop.com/', clicks=Decimal('2'))] * 150
    monkeypatch.setattr(context, 'GoogleReports', lambda: report)
    contracts = []
    def ga4(_report, connection, contract, start, end):
        contracts.append(contract)
        return {'rows': [{}] * 150, 'total_rows': 150, 'quality': 'GA4 verified'}
    monkeypatch.setattr(context, '_ga4', ga4)
    value = context.context(TODAY)
    json.dumps(value)
    assert set(value['markets']) == {'AU', 'US', 'UK'}
    assert len(contracts) == 6
    assert all(('sessionSource', 'EXACT', 'google') in c.filters for c in contracts)
    for market in value['markets'].values():
        current, prior = market['current'], market['prior']
        assert date.fromisoformat(prior['end']) + timedelta(days=1) == date.fromisoformat(current['start'])
        assert len(current['gsc']['rows']) == 100
        assert len(current['ga4_organic_landing_pages']['rows']) == 100
