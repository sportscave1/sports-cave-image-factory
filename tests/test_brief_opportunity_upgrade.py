"""Synthetic end-to-end contracts for fresh designs and calendar-led product ads."""
import json
from datetime import date, timedelta
from unittest.mock import Mock

import pytest
import home_sports_morning_brief as sports
import home_meta_morning_brief as meta
import home_brief_opportunities as opportunities
import morning_design_queue as queue
from tests.test_auto_editions_jobs import database  # noqa: F401

TODAY = date(2026, 11, 19)


def article(subject='Test Star', market='USA'):
    return dict(title=subject + ' — Lasting Legacy', subject=subject, sport='NBA', markets=[market],
                primary_market=market, recommendation='A verified new collector concept.',
                links=[dict(label='Source', url='https://example.test/news')],
                sales_rationale='Established star recognition; demand remains a research hypothesis.',
                opportunity_status='Research first')


def edition():
    return dict(date=str(TODAY), summary='A concise summary across Australia, the USA and UK.',
                full_brief='Sports news. Legends research. Rivalries research.',
                recommendations=[article('News Star')], rivalries=[article('Test rivalry')],
                design_recommendations=[article(f'Star {n}') for n in range(4)])


def test_four_same_market_designs_keep_sales_rank_and_queue_status():
    from home_morning_brief_actions import brief_html
    value = sports.parse_edition(json.dumps(edition()), TODAY)
    key = queue.identity(str(TODAY), 'design_recommendations', value['design_recommendations'][0])
    html = brief_html(value, editions=[value], today=TODAY, design_statuses={key: 'Ready for review'})
    panel = html.split('aria-label="Design recommendations"')[1].split('</section>')[0]
    assert panel.count('data-design-key=') == 4
    assert 'Ready for review' in panel and 'Sales potential' in panel
    assert [panel.index(f'{n+1}. Star {n}') for n in range(4)] == sorted(panel.index(f'{n+1}. Star {n}') for n in range(4))
    assert 'News Star' not in panel and 'Test rivalry' not in panel
    assert 'Read the full Morning Brief' in html and 'Rivalries Brief' in html
    assert sports.design_sections(value) == ('design_recommendations',)


def test_new_designs_reject_duplicate_subject_and_oversized_rivalries():
    value = edition()
    value['design_recommendations'][1]['subject'] = 'Star 0'
    with pytest.raises(ValueError, match='distinct subject'):
        sports.parse_edition(json.dumps(value), TODAY)
    value = edition()
    value['rivalries'] *= 4
    with pytest.raises(ValueError, match='up to three'):
        sports.parse_edition(json.dumps(value), TODAY)


def test_seven_day_exclusion_includes_legacy_and_renamed_designs(database, monkeypatch):
    jobs, sql = database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY, value jsonb, updated_at timestamptz)')
    old = dict(date=str(TODAY-timedelta(days=7)), recommendations=[], legends=[article('Star 0')])
    sql.execute('INSERT INTO app_settings VALUES (%s,%s::jsonb,now())',
                ('home_sports_morning_brief:'+old['date'],json.dumps(old)))
    with jobs.connect() as conn, conn.cursor() as cur:
        with pytest.raises(ValueError, match='last seven days'):
            sports.validate_fresh_designs(edition(), cur)
    sql.execute('DELETE FROM app_settings')
    old['date'] = str(TODAY-timedelta(days=8))
    sql.execute('INSERT INTO app_settings VALUES (%s,%s::jsonb,now())',
                ('home_sports_morning_brief:'+old['date'],json.dumps(old)))
    with jobs.connect() as conn, conn.cursor() as cur:
        sports.validate_fresh_designs(edition(), cur)


def ad():
    return dict(sport='NBA', market='USA', event_title='NBA regular season', product_title='Test Star Wall Art',
                product_url='https://www.sportscaveshop.com/products/test-star',
                collection_url='https://www.sportscaveshop.com/collections/nba',
                rationale='A live season and a recognisable collector subject.',
                performance_evidence='Unproven test; no exact product purchase history verified.',
                action='Test the established portrait format with US basketball collectors.')


def test_ad_schema_links_distinct_sports_and_qualitative_evidence():
    value = dict(date=str(TODAY),report_date=str(TODAY-timedelta(days=1)),roas=None,orders=None,
                 actions=[],summary='Review the strongest live catalogue opportunities.',recommendations=[],
                 ad_recommendations=[ad()])
    assert meta.parse_edition(json.dumps(value), TODAY)['ad_recommendations'] == [ad()]
    value['ad_recommendations'] *= 2
    with pytest.raises(ValueError, match='distinct live sport'):
        meta.parse_edition(json.dumps(value), TODAY)


def test_ad_eligibility_checks_calendar_publication_and_collection(database, monkeypatch):
    jobs, sql = database
    monkeypatch.setattr(opportunities, 'connect', jobs.connect)
    sql.execute('CREATE TABLE shopify_products(handle text,title text,status text,online_store_url text,raw_json jsonb)')
    sql.execute('INSERT INTO shopify_products VALUES (%s,%s,%s,%s,%s::jsonb)',
                ('test-star','Test Star Wall Art','ACTIVE',ad()['product_url'],
                 json.dumps(dict(collections=[dict(handle='nba',title='NBA')]))))
    opportunities.validate_ad_products([ad()],TODAY)
    with pytest.raises(ValueError, match='Live Home calendar'):
        opportunities.validate_ad_products([dict(ad(), event_title='An invented final')], TODAY)
    sql.execute("UPDATE shopify_products SET status='DRAFT'")
    with pytest.raises(ValueError, match='active and published'):
        opportunities.validate_ad_products([ad()],TODAY)
    sql.execute("UPDATE shopify_products SET status='ACTIVE', raw_json='{}'")
    with pytest.raises(ValueError, match='specified sport collection'):
        opportunities.validate_ad_products([ad()],TODAY)


def test_archived_date_can_be_read_after_latest_advances(monkeypatch):
    import crm_growth_reporting as growth
    old = dict(date='2026-11-12',recommendations=[])
    monkeypatch.setattr(growth, 'get_app_setting', lambda key, **kw: old if key.endswith(':2026-11-12') else dict(date=str(TODAY)))
    assert growth.published_sports_edition(date(2026,11,12)) == old


def test_hosted_same_day_contract_upgrade_is_once_only(database, monkeypatch):
    import daily_brief_worker as worker
    import supabase_backend as db
    import os_accounts
    jobs, sql = database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz)')
    owner = dict(email='owner@example.test',role='admin',session_version=1)
    for key in os_accounts.REPORTING_OWNER_ENV_KEYS:
        monkeypatch.setenv(key,owner['email'])
    for module in (worker,sports,db):
        monkeypatch.setattr(module,'connect',jobs.connect)
        if hasattr(module,'sydney_date'):
            monkeypatch.setattr(module,'sydney_date',lambda:TODAY)
    monkeypatch.setattr(os_accounts.DEFAULT_STORE,'get_user',lambda _:owner)
    monkeypatch.setattr(os_accounts,'can_access_page',lambda *_:True)
    old = dict(date=str(TODAY),full_brief='Legacy edition.',recommendations=[article('Earlier story')])
    claims = dict(sub='owner',version='1')
    worker.enqueue('sports',old,claims)
    assert worker.process_one() and worker.status('sports')['format_version'] == 1
    worker.enqueue('sports',edition(),claims)
    assert worker.process_one()
    state = worker.status('sports')
    assert state['verified'] and state['format_version'] == 2 and state['matches_submission']
    assert worker.enqueue('sports',edition(),claims)['status'] == 'completed'
    changed = edition()
    changed['summary'] = 'Another conflicting correction.'
    with pytest.raises(ValueError,match='already exists'):
        worker.enqueue('sports',changed,claims)
