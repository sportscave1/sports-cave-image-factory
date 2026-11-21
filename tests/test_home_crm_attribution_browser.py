"""Offline layout check for the visible attribution disagreement explanation."""
from datetime import date
from playwright.sync_api import sync_playwright, expect
from home_crm_reporting import ledger
from home_crm_ui import CSS, html


def test_source_comparison_stays_visible_on_mobile(tmp_path):
    rows=[{"dimensions":{"transactionId":str(i),"sessionSourceMedium":"google / cpc",
        "deviceCategory":"mobile"},"metrics":{"ecommercePurchases":"1"}} for i in (1,2,3)]
    report=ledger({"1","2","3"},rows,{
        "1":{"channel":"Google paid","reason":"explicit_paid_tags"},
        "2":{"channel":"Organic","reason":"explicit_organic_evidence"},
        "3":{"channel":"Unresolved","reason":"google_listing_paid_status_unknown"}})
    data={"start":"2026-11-14","end":"2026-11-20","checked_at":"2026-11-21T04:00:00Z",
        "ledger":report,"roas":{"google":3.5,"facebook":2},
        "coverage":{"ga4":{"status":"verified"},"google":{"status":"verified","purchases":2.5}}}
    markup='<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:12px;font:14px Arial}*{box-sizing:border-box}</style>'+CSS+html(date(2026,11,21),{"state":"ready","data":data})
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="msedge",headless=True)
        try:
            page=browser.new_page()
            page.route("**/*",lambda route:route.abort())
            page.set_content(markup)
            comparison=page.locator('.sc-crm-comparison')
            warning=page.locator('.sc-crm-warning')
            expect(comparison).to_contain_text('Shopify last visit 1 · GA4 purchase session 3')
            expect(comparison).to_contain_text('Google Ads: 2.5 attributed purchases (ad interaction dates)')
            expect(warning).to_contain_text('1 order has paid/organic model differences')
            expect(warning).to_contain_text('Google listing order has unverified paid/organic status')
            expect(page.locator('[data-channel="Organic"]')).to_contain_text('Organic (last visit)')
            for width in (1600,820,390,320):
                page.set_viewport_size({"width":width,"height":900})
                assert page.evaluate('document.documentElement.scrollWidth')<=width
                expect(comparison).to_be_visible()
                expect(warning).to_be_visible()
            page.screenshot(path=str(tmp_path/'crm-attribution-mobile.png'),full_page=True)
        finally:
            browser.close()
