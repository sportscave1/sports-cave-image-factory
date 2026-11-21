"""Published Home markup in a browser; all network traffic is intercepted."""
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from playwright.sync_api import sync_playwright, expect
import home_meta_morning_brief as meta
import home_sports_morning_brief as sports
import os_accounts
from tests.test_brief_opportunity_upgrade import edition, ad
from tests.test_all_live_ad_recommendations import row


def test_saved_briefs_have_no_provider_reads_and_fit_mobile(monkeypatch, tmp_path):
    today = date(2026, 11, 18)
    monkeypatch.setattr(meta, 'can_view', lambda user: True)
    monkeypatch.setattr(os_accounts, 'is_reporting_owner', lambda user: True)
    monkeypatch.setattr(os_accounts, 'can_access_page', lambda *a: True)
    for module in (sports, meta):
        monkeypatch.setattr(module, 'get_app_setting', Mock(side_effect=AssertionError('render attempted storage')))
    st = Mock()
    saved_sports = dict(edition(), date=str(today))
    sports.render(st, {}, today, snapshot=dict(saved=saved_sports, editions=[], statuses={}))
    # Old reporting data previously triggered provider reads automatically on Home.
    meta.render(st, {}, today, snapshot=dict(saved=dict(date='2026-11-16',report_date='2026-11-15',
        roas=None,orders=None,actions=[],summary='Review the saved recommendations.',
        recommendations=[],ad_recommendations=[row(),
            dict(ad(),sport='Cricket',market='AUS',product_title='Australia Top Design',product_url='https://www.sportscaveshop.com/products/australia-top',collection_url='https://www.sportscaveshop.com/collections/cricket',event_title="Women's Big Bash League"),
            dict(ad(),sport='Football',market='UK',product_title='UK Top Design',product_url='https://www.sportscaveshop.com/products/uk-top',collection_url='https://www.sportscaveshop.com/collections/football',event_title='Premier League season'),
            dict(ad(),sport='NFL',market='USA',product_title='Lower-ranked USA Design',product_url='https://www.sportscaveshop.com/products/lower-usa',collection_url='https://www.sportscaveshop.com/collections/nfl',event_title='NFL regular season')]),refresh=''))
    fragments = ''.join(call.args[0] for call in st.html.call_args_list)
    html = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:12px;font:14px Arial}*{box-sizing:border-box}</style>'+fragments
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge', headless=True)
        try:
            page=browser.new_page()
            requests=[]
            def route(request):
                if request.request.url=='http://fixture.test/':
                    request.fulfill(body=html,content_type='text/html')
                else:
                    requests.append(request.request.url)
                    request.fulfill(json=dict(state='ready',data=dict(start='2026-11-17',end='2026-11-17',checked_at='2026-11-18T00:00:00Z',
                        ledger=dict(rows=[dict(channel='Google paid',mobile=1,desktop=2,other=0,total=3)],orders=3,matched=3,unmatched=0),
                        roas=dict(facebook=2.0,google=3.5),coverage={},basis='Synthetic order matches')))
            page.route('**/*',route)
            page.goto('http://fixture.test/')
            expect(page.locator('.sc-meta-review')).to_contain_text('Review the saved recommendations.')
            expect(page.locator('.sc-legends .sc-brief-row')).to_have_count(4)
            expect(page.locator('.sc-daily-summary')).to_contain_text('A concise summary')
            expect(page.locator('.sc-meta-review')).to_contain_text('Test Star Wall Art')
            expect(page.locator('.sc-ad-preview')).to_have_count(3)
            expect(page.locator('.sc-ad-preview').nth(0)).to_contain_text('Australia Top Design')
            expect(page.locator('.sc-ad-preview').nth(1)).to_contain_text('Test Star Wall Art')
            expect(page.locator('.sc-ad-preview').nth(2)).to_contain_text('UK Top Design')
            expect(page.get_by_role('dialog',name='All ad recommendations')).not_to_be_visible()
            page.locator('.sc-meta-review > details > summary').click()
            page.get_by_role('button',name='See more',exact=True).click()
            popup=page.get_by_role('dialog',name='All ad recommendations')
            expect(popup).to_be_visible()
            expect(popup.get_by_text('Lower-ranked USA Design',exact=True)).to_be_visible()
            expect(popup.get_by_text('Another Star Wall Art',exact=True)).to_be_visible()
            expect(popup.get_by_text('Live basketball creates a timely collector opportunity.',exact=True)).not_to_be_visible()
            popup.locator('.sc-ad-detail summary').first.click()
            expect(popup.get_by_text('Live basketball creates a timely collector opportunity.',exact=True)).to_be_visible()
            for width in (1600,820,390,320):
                page.set_viewport_size(dict(width=width,height=900))
                assert page.evaluate('document.documentElement.scrollWidth')<=width
                assert popup.evaluate('(e)=>e.scrollWidth<=e.clientWidth')
            popup.get_by_role('button',name='Close',exact=True).click()
            expect(popup).not_to_be_visible()
            page.get_by_role('button',name='Read the full Morning Brief').click()
            expect(page.get_by_role('dialog',name='Full Sports Morning Brief')).to_contain_text('Rivalries Brief')
            page.get_by_role('dialog',name='Full Sports Morning Brief').get_by_role('button',name='Close',exact=True).click()
            for width in (1600, 820, 390, 320):
                page.set_viewport_size(dict(width=width,height=900))
                assert page.evaluate('document.documentElement.scrollWidth') <= width
            assert requests and all('/ops/meta-morning-brief/results?' in url for url in requests)
            page.get_by_label('CRM reporting period').select_option('week')
            expect(page.locator('[data-roas="facebook"]')).to_have_text('2.00×')
            expect(page.locator('[data-roas="google"]')).to_have_text('3.50×')
            page.get_by_role('button',name='Refresh',exact=True).click()
            page.wait_for_timeout(100)
            assert any('refresh=1' in url for url in requests)
            page.screenshot(path=str(tmp_path/'home-saved-briefs-mobile.png'))
        finally:
            browser.close()
