from copy import deepcopy
from datetime import date
import json
from unittest.mock import Mock
import pytest

import os_accounts
import seo_companion as jobs
import seo_companion_audit as audit
from seo_technical_audit import CrawlResponse, RequestBudgetExceeded
from tests.test_auto_editions_jobs import database  # noqa: F401

ORIGIN = audit.ORIGIN
TARGET = ORIGIN + '/products/peter-brock-tribute-art'
OWNER = {'id': 'owner', 'role': 'admin', 'email': 'owner@example.test', 'session_version': 1}
DAY = date(2026, 11, 21)


class Crawler:
    def __init__(self, pages):
        self.pages = pages
        self.stats = {'total_storefront_requests': 0}
        self._page_cache = {}
        self.visited = []

    def fetch_page(self, url):
        self.visited.append(url)
        self.stats['total_storefront_requests'] += 1
        status, text = self.pages.get(url, (404, ''))
        return CrawlResponse(status, {'content-type': 'text/html'}, text, url)


def pages():
    return {
        ORIGIN + '/robots.txt': (200, 'User-agent: *\nAllow: /\nDisallow: /pages/private'),
        ORIGIN + '/sitemap.xml': (200, '<sitemapindex><sitemap><loc>' + ORIGIN + '/sitemap_pages_1.xml</loc></sitemap></sitemapindex>'),
        ORIGIN + '/sitemap_pages_1.xml': (200, '<urlset><url><loc>' + ORIGIN + '/pages/editorial</loc></url></urlset>'),
        ORIGIN + '/': (200, '<a href="/pages/editorial">Editorial</a><a href="/pages/private">Private</a><a href="https://evil.example/">External</a><a href="/account">Account</a>'),
        ORIGIN + '/collections': (200, '<a href="/collections/v8-supercars-wall-art">V8</a>'),
        ORIGIN + '/collections/v8-supercars-wall-art': (200, '<a href="/products/peter-brock-tribute-art?variant=123#buy"><img alt="Peter Brock edition"></a>'),
        ORIGIN + '/pages/editorial': (200, '<a href="https://sportscaveshop.com/products/peter-brock-tribute-art">Brock tribute</a>'),
        TARGET: (404, '<h1>Not found</h1>'),
    }


def job():
    return {'id': str(DAY), 'date': str(DAY), 'targets': [TARGET], 'started_at': '2026-11-21T04:00:00+00:00'}


def test_audit_finds_anchor_and_before_values_without_writes():
    crawler = Crawler(pages())
    result = audit.audit(job(), crawler=crawler)
    assert result['targets'][0]['status'] == 404
    assert {r['anchor'] for r in result['links']} == {'Peter Brock edition', 'Brock tribute'}
    assert result['storefront_changes'] == 0
    assert len(result['proposals']) == 3
    assert result['proposals'][0]['before'] == '/products/peter-brock-tribute-art?variant=123#buy'
    assert all('evil.example' not in u and '/account' not in u and '/pages/private' not in u for u in crawler.visited)
    assert not result['coverage_complete']  # robots excluded a discovered source.
    json.dumps(result)


def test_audit_does_not_claim_no_links_beyond_capped_scope():
    result = audit.audit(job(), crawler=Crawler(pages()), max_pages=1)
    assert not result['coverage_complete'] and result['remaining_sources'] > 0
    assert any('limit' in gap for gap in result['gaps'])


@pytest.mark.parametrize('url', ['https://evil.example/a', 'http://www.sportscaveshop.com/a',
    'https://www.sportscaveshop.com@127.0.0.1/a', 'https://www.sportscaveshop.com:444/a',
    'https://www.sportscaveshop.com/admin', 'https://www.sportscaveshop.com/checkouts/a'])
def test_public_url_boundary(url):
    with pytest.raises(ValueError):
        audit.public_url(url)


def test_public_crawler_rejects_mutations_and_external_requests():
    crawler = audit.PublicCrawler(Mock(headers={}), request_interval_seconds=0)
    with pytest.raises(ValueError):
        crawler._request_once('POST', TARGET)
    with pytest.raises(ValueError):
        crawler._request_once('GET', 'https://evil.example/')


def test_stop_is_not_a_completed_audit():
    with pytest.raises(InterruptedError):
        audit.audit(job(), crawler=Crawler(pages()), stopped=lambda: True)


def test_robots_specific_rules_wildcards_and_agent_groups():
    rules = audit.Robots(['User-agent: *', 'Allow: /', 'Disallow: /pages/*private$',
                         'Disallow: /pages/no', 'Allow: /pages/no-public',
                         'User-agent: OtherBot', 'Disallow: /'])
    assert not rules.can_fetch(audit.AGENT, ORIGIN + '/pages/is-private')
    assert rules.can_fetch(audit.AGENT, ORIGIN + '/pages/is-private-more')
    assert rules.can_fetch(audit.AGENT, ORIGIN + '/pages/no-public')
    assert not rules.can_fetch('OtherBot', ORIGIN + '/pages/no-public')
    empty_specific = audit.Robots(['User-agent: ' + audit.AGENT, 'Disallow:', 'User-agent: *', 'Disallow: /'])
    assert empty_specific.can_fetch(audit.AGENT, ORIGIN + '/')


def test_revision_survives_jsonb_number_normalisation():
    assert jobs.revision({'duration_seconds': 0.0}) == jobs.revision({'duration_seconds': 0})


def test_source_discovery_excludes_collection_product_duplicates_and_query_traps():
    assert not audit.source_url(ORIGIN + '/collections/v8/products/another-edition')
    assert not audit.source_url(ORIGIN + '/collections/v8?sort_by=price')
    assert audit.source_url(ORIGIN + '/blogs/news/brock-story')


def test_shopify_image_sitemap_locations_do_not_stop_page_discovery():
    data = pages()
    data[ORIGIN + '/sitemap_pages_1.xml'] = (200, '<urlset xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
        '<url><loc>' + ORIGIN + '/pages/editorial</loc><image:image><image:loc>https://cdn.shopify.com/image.jpg</image:loc></image:image></url>'
        '<url><loc>' + ORIGIN + '/pages/second-story</loc></url></urlset>')
    data[ORIGIN + '/pages/second-story'] = (200, '<h1>Second</h1>')
    crawler = Crawler(data)
    result = audit.audit(job(), crawler=crawler)
    assert ORIGIN + '/pages/second-story' in crawler.visited
    assert not any('Sitemap could not be read' in gap for gap in result['gaps'])
    assert not any('cdn.shopify.com' in url for url in crawler.visited)


def test_unverified_target_does_not_become_broken_page_proposal():
    crawler = Crawler(pages())
    fetch = crawler.fetch_page
    def failing(url):
        if url == TARGET:
            raise TimeoutError
        return fetch(url)
    crawler.fetch_page = failing
    result = audit.audit(job(), crawler=crawler)
    assert result['targets'][0]['status'] is None
    assert [r['kind'] for r in result['proposals']] == ['verification_gap']


@pytest.fixture
def storage(database, monkeypatch):
    backend, sql = database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)')
    monkeypatch.setattr(jobs, 'connect', backend.connect)
    monkeypatch.setattr('supabase_backend.connect', backend.connect)
    monkeypatch.setattr('sports_sales_calendar.sydney_date', lambda: DAY)
    monkeypatch.setattr(os_accounts, 'is_reporting_owner', lambda user: user == OWNER)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *_: True)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE, 'get_user', lambda _: OWNER)
    report = {'date': str(DAY), 'summary': 'Audit retired Brock edition.',
              'next_action': 'Audit inbound Brock links; prepare fixes for review.',
              'opportunities': [{'url': TARGET}]}
    sql.execute('INSERT INTO app_settings VALUES($1,$2::jsonb,now())', ('home_seo_daily_report', json.dumps(report)))
    return sql


def read(key):
    with jobs.connect() as conn, conn.cursor() as cur:
        return jobs._setting(cur, key)


def test_enable_queues_once_and_pause_prevents_new_claims(storage):
    assert jobs.claim() is None
    first = jobs.configure(OWNER, True)
    assert first['stage'] == 'queued'
    assert jobs.configure(OWNER, True) == first
    jobs.configure(OWNER, False)
    assert jobs.claim() is None
    assert len(jobs.snapshot()['jobs']) == 1


def test_queue_recovers_latest_report_and_claims_only_once(storage):
    jobs.configure(OWNER, True)
    storage.execute('DELETE FROM app_settings WHERE key=$1', (jobs.PREFIX + str(DAY),))
    first = jobs.claim()
    assert first['targets'] == [TARGET] and first['attempts'] == 1
    assert jobs.claim() is None
    storage.execute("UPDATE app_settings SET updated_at=now()-interval '16 minutes' WHERE key=$1", (jobs.PREFIX + str(DAY),))
    second = jobs.claim()
    assert second['attempts'] == 2 and second['lease'] != first['lease']
    with pytest.raises(InterruptedError):
        jobs._checkpoint(first, progress={'pages_checked': 123})


def test_completed_evidence_review_and_revision_guard(storage):
    jobs.configure(OWNER, True)
    claimed = jobs.claim()
    result = audit.audit(job(), crawler=Crawler(pages()))
    jobs._checkpoint(claimed, result=result)
    assert jobs.snapshot()['jobs'][0]['stage'] == 'ready_for_review'
    jobs.review(OWNER, claimed['id'], '1', 'Changes requested', jobs.revision(result))
    saved = jobs.snapshot()['reviews'][0]
    assert saved['decision'] == 'Changes requested'
    with pytest.raises(ValueError, match='changed'):
        jobs.review(OWNER, claimed['id'], '1', 'Approved for implementation', 'stale-revision')
    assert read(jobs.PREFIX + str(DAY))['result']['storefront_changes'] == 0


def test_permission_checked_before_any_network_work(storage, monkeypatch):
    jobs.configure(OWNER, True)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *_: False)
    crawler = Mock(side_effect=AssertionError('Network must not be opened'))
    monkeypatch.setattr(audit, 'PublicCrawler', crawler)
    assert jobs.process_one()
    crawler.assert_not_called()
    assert jobs.snapshot()['jobs'][0]['stage'] == 'retrying'


def test_audit_runs_to_saved_result_on_existing_worker(storage, monkeypatch):
    jobs.configure(OWNER, True)
    monkeypatch.setattr(audit, 'PublicCrawler', lambda *_args, **_kwargs: Crawler(pages()))
    assert jobs.process_one()
    saved = jobs.snapshot()['jobs'][0]
    assert saved['stage'] == 'ready_for_review'
    assert len(saved['result']['links']) == 2


def test_next_daily_publication_queues_work_atomically(storage, monkeypatch):
    import home_seo_report
    jobs.configure(OWNER, True)
    tomorrow = date(2026, 11, 22)
    monkeypatch.setattr('sports_sales_calendar.sydney_date', lambda: tomorrow)
    edition = {'date': str(tomorrow), 'period_start': '2026-10-22', 'period_end': '2026-11-18',
               'summary': 'Inspect the retired edition.', 'next_action': 'Check inbound links for review.',
               'source_gaps': [], 'opportunities': [{'url': TARGET, 'query': 'peter brock merchandise', 'market': 'AU',
                    'evidence': 'Verified final report.', 'action': 'Audit inbound links.', 'availability': 'Draft; recheck required.'}]}
    home_seo_report.publish(json.dumps(edition), OWNER)
    queued = read(jobs.PREFIX + str(tomorrow))
    assert queued['stage'] == 'queued' and queued['targets'] == [TARGET]
    home_seo_report.publish(json.dumps(edition), OWNER)
    assert read(jobs.PREFIX + str(tomorrow)) == queued
