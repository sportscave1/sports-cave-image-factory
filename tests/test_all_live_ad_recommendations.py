import json
from datetime import date
from unittest.mock import MagicMock
import pytest
from playwright.sync_api import sync_playwright, expect
import home_meta_morning_brief as meta
import home_brief_opportunities as opportunities
from home_brief_calendar import ScheduleEvent
from tests.test_brief_opportunity_upgrade import ad
from tests.test_auto_editions_jobs import database  # noqa: F401

TODAY = date(2026,11,19)


def row():
    return dict(ad(),sport_summary='Live basketball creates a timely collector opportunity.',
                secondary_product=dict(ad(), product_title='Another Star Wall Art',
                    product_url='https://www.sportscaveshop.com/products/another-star',
                    ad_coverage='not_found_in_reviewed_ads',
                    ad_coverage_evidence='No exact product match in the reviewed active and paused ads. Unmapped canvas destinations remain unknown.'))


def test_inventory_outage_allows_one_verified_secondary_enrichment():
    from daily_brief_worker import contract_upgrade
    prior=dict(ad_format_version=3,ad_recommendations=[dict(ad(),secondary_reason='Inventory unavailable.')])
    enriched=dict(ad_format_version=3,ad_recommendations=[row()])
    assert contract_upgrade('meta',prior,enriched)
    assert not contract_upgrade('meta',enriched,enriched)
    assert not contract_upgrade('meta',prior,prior)


def test_secondary_is_distinct_and_requires_explicit_review_evidence():
    parsed=meta._ad_recommendations([row()],all_live=True)
    assert parsed[0]['secondary_product']['product_title']=='Another Star Wall Art'
    value=row(); value['secondary_product']['product_url']=value['product_url']
    with pytest.raises(ValueError,match='different'):
        meta._ad_recommendations([value],all_live=True)
    value=row(); value['secondary_product'].pop('ad_coverage_evidence')
    with pytest.raises(ValueError,match='coverage evidence'):
        meta._ad_recommendations([value],all_live=True)
    with pytest.raises(ValueError,match='sport_summary'):
        meta._ad_recommendations([ad()],all_live=True)


def test_all_live_coverage_does_not_silently_omit_sports(monkeypatch):
    events=[ScheduleEvent(s,('USA',),s+' season',date(2026,1,1),date(2026,12,31),'https://example.test')
            for s in ('NBA','NFL','Ice Hockey','Baseball','NASCAR','Golf')]
    monkeypatch.setattr(opportunities,'live_events',lambda _:events)
    with pytest.raises(ValueError,match='every Live'):
        opportunities.validate_ad_products([ad()],TODAY,require_all=True)
    gaps=[dict(sport=e.sport,market='USA',event_title=e.title,sport_summary='Live season.',unavailable_reason='No suitable live product verified.') for e in events]
    connection=MagicMock()
    monkeypatch.setattr(opportunities,'connect',connection)
    opportunities.validate_ad_products(meta._ad_recommendations(gaps,all_live=True),TODAY,require_all=True)


def test_more_than_four_sports_are_compact_with_individual_read_more(monkeypatch,tmp_path):
    from home_brief_calendar import load_schedule
    events=opportunities.live_events(TODAY)
    rows=[row()]
    seen={'NBA'}
    for event in events:
        if event.sport not in seen:
            rows.append(dict(sport=event.sport,market='USA',event_title=event.title,sport_summary='Live sport summary.',unavailable_reason='Catalogue review gap.'))
            seen.add(event.sport)
    value=dict(date=str(TODAY),report_date='2026-11-18',roas=None,orders=None,actions=[],summary='All live sports reviewed.',recommendations=[],ad_format_version=3,ad_recommendations=rows)
    parsed=meta.parse_edition(json.dumps(value),TODAY)
    markup=meta.ad_rows_html(parsed,TODAY)
    assert len(rows)>4 and 'More recommendations' not in markup
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda route:route.fulfill(body='<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font:14px Arial;overflow-wrap:anywhere}.sc-ad-sr{display:none}</style>'+markup,content_type='text/html'))
        page.goto('http://fixture.test/')
        expect(page.locator('.sc-ad-sport')).to_have_count(len({e.sport for e in events}))
        expect(page.get_by_text('Another Star Wall Art',exact=True)).to_be_visible()
        expect(page.get_by_text('Live basketball creates a timely collector opportunity.',exact=True)).not_to_be_visible()
        page.locator('.sc-ad-detail summary').first.click()
        expect(page.get_by_text('Live basketball creates a timely collector opportunity.',exact=True)).to_be_visible()
        for width in (1600,820,390,320):
            page.set_viewport_size(dict(width=width,height=900))
            assert page.evaluate('document.documentElement.scrollWidth')<=width
        page.screenshot(path=str(tmp_path/'all-live-ads.png'))
        browser.close()


def test_same_day_four_product_edition_upgrades_to_all_live_once(database,monkeypatch):
    import daily_brief_worker as worker
    import supabase_backend as db
    import os_accounts
    jobs,sql=database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz)')
    owner=dict(email='owner@example.test',role='admin',session_version=1)
    for key in os_accounts.REPORTING_OWNER_ENV_KEYS:
        monkeypatch.setenv(key,owner['email'])
    for module in (worker,meta,db,opportunities):
        monkeypatch.setattr(module,'connect',jobs.connect)
        if hasattr(module,'sydney_date'):
            monkeypatch.setattr(module,'sydney_date',lambda:TODAY)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE,'get_user',lambda _:owner)
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *_:True)
    monkeypatch.setattr(os_accounts,'can_access_reporting',lambda *_:True)
    monkeypatch.setattr(meta,'account_roas',lambda *_:None)
    monkeypatch.setattr(meta,'device_orders',lambda *_:None)
    value=dict(date=str(TODAY),report_date='2026-11-18',roas=None,orders=None,actions=[],summary='Review live sports.',recommendations=[],ad_recommendations=[])
    claims=dict(sub='owner',version='1')
    worker.enqueue('meta',value,claims)
    assert worker.process_one() and worker.status('meta')['format_version']==2
    seen=set(); rows=[]
    for e in opportunities.live_events(TODAY):
        if e.sport in seen: continue
        seen.add(e.sport)
        market=next(m for m in ('AUS','USA','UK') if m in e.markets or 'ALL' in e.markets)
        rows.append(dict(sport=e.sport,market=market,event_title=e.title,sport_summary='Live season reviewed.',unavailable_reason='No suitable catalogue product verified in this synthetic review.'))
    value=dict(value,ad_format_version=3,ad_recommendations=rows)
    worker.enqueue('meta',value,claims)
    assert worker.process_one()
    state=worker.status('meta')
    assert state['verified'] and state['format_version']==3 and state['matches_submission']
    with pytest.raises(ValueError,match='already exists'):
        worker.enqueue('meta',dict(value,summary='A conflicting correction.'),claims)
