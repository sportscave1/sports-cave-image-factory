from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pytest
from playwright.sync_api import sync_playwright, expect
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from test_auto_editions_jobs import database
import home_refresh_queue as refresh


@pytest.fixture
def store(database, monkeypatch):
    db, cur = database
    cur.execute((Path(__file__).parents[1] / 'migrations/20261117150000_morning_design_queue.sql').read_text())
    cur.execute('''CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz);
        CREATE TABLE product_upload_desktop(singleton boolean,actor_id text);
        INSERT INTO product_upload_desktop VALUES(true,'synthetic');
        CREATE TABLE shopify_products(shopify_product_id text PRIMARY KEY,title text,handle text,status text)''')
    for n in range(1, 324):
        cur.execute('INSERT INTO shopify_products VALUES(%s,%s,%s,%s)',
                    ('gid://shopify/Product/'+str(n), f'Design {n:03}', f'design-{n}', 'active' if n<=322 else 'archived'))
    monkeypatch.setattr(refresh, 'connect', db.connect)
    monkeypatch.setattr(refresh, 'companion', lambda: ({str(n) for n in range(1, 212)}, {'state':'ready'}))
    return cur


def test_unverified_pagination_manual_add_and_idempotent_queue(store):
    first = refresh.listing()
    assert first['total'] == 111 and len(first['rows']) == 40
    rows = first['rows'] + refresh.listing(offset=40)['rows'] + refresh.listing(offset=80)['rows']
    assert len({r['product_id'] for r in rows}) == 111
    assert refresh.listing(all_designs=True)['total'] == 322
    assert refresh.listing('Design 001', all_designs=True)['rows'][0]['product_id'] == '1'
    refresh.change('1', 'add')
    assert refresh.listing()['total'] == 112
    store.execute('SELECT count(*) AS n FROM morning_design_jobs')
    assert store.fetchone()['n'] == 0
    assert refresh.change('212','enqueue') == {'added':True,'stage':0}
    assert refresh.change('gid://shopify/Product/212','enqueue') == {'added':False,'stage':0}
    store.execute('SELECT * FROM morning_design_jobs')
    jobs = store.fetchall()
    assert len(jobs) == 1 and jobs[0]['section'] == 'refresh'
    from morning_design_queue import _waiting_prompt
    assert _waiting_prompt(jobs[0]) == jobs[0]['prompt']
    assert 'existing_product_refresh' in jobs[0]['prompt']
    assert 'morning_design_job_id = "'+refresh.job_id('212')+'"' in jobs[0]['prompt']
    assert 'not an artwork quality judgement' in jobs[0]['prompt']
    with pytest.raises(ValueError): refresh.change('323','enqueue')


def test_api_owner_origin_and_validation(monkeypatch):
    import files_upload_api, os_accounts
    monkeypatch.setattr(files_upload_api, '_request_user', lambda *a,**k: {'id':'test'})
    monkeypatch.setattr(os_accounts, 'is_reporting_owner', lambda _: False)
    client = TestClient(Starlette(routes=[Route('/queue',refresh.api,methods=['GET','POST'])]))
    assert client.get('/queue').status_code == 403
    monkeypatch.setattr(os_accounts, 'is_reporting_owner', lambda _: True)
    assert client.post('/queue').status_code == 403
    assert client.post('/queue',headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.get('/queue?offset=-1').status_code == 400
    monkeypatch.setattr(refresh, 'listing', lambda *a: {'rows':[],'total':0})
    assert client.get('/queue').json()['total'] == 0


def test_popup_lazy_bounded_search_and_queue(tmp_path):
    from home_design_refresh import render_html
    html = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+render_html(None)
    calls=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge', headless=True)
        page=browser.new_page(viewport={'width':390,'height':800})
        def route(r):
            if r.request.url=='http://fixture.test/':
                return r.fulfill(body=html,content_type='text/html')
            calls.append(r.request)
            if r.request.method=='POST':return r.fulfill(json={'added':True,'stage':0})
            query=parse_qs(urlparse(r.request.url).query)
            rows=[dict(product_id=str(n),title=f'Design {n} <script>',stage=None) for n in range(40)]
            if query.get('q'):rows=rows[:1]
            return r.fulfill(json={'rows':rows,'total':len(rows),'next_offset':None})
        page.route('**/*',route)
        page.goto('http://fixture.test/')
        assert not calls
        page.get_by_role('button',name='Designs to Refresh').click()
        expect(page.locator('.sc-refresh-list .sc-refresh-row')).to_have_count(40)
        assert page.locator('.sc-refresh-list').evaluate('(e)=>e.scrollHeight>e.clientHeight')
        assert page.evaluate('document.documentElement.scrollWidth') == 390
        page.get_by_role('button',name='Add to queue',exact=True).first.click()
        expect(page.get_by_role('button',name='Queued',exact=True)).to_be_disabled()
        page.get_by_label('Search refresh list').fill('Design 1')
        expect(page.locator('.sc-refresh-list .sc-refresh-row')).to_have_count(1)
        page.get_by_text('Add a design',exact=True).click()
        page.get_by_label('Search all designs').fill('Design 2')
        expect(page.locator('.sc-refresh-picker-list .sc-refresh-row')).to_have_count(1)
        page.get_by_role('button',name='Add to list',exact=True).click()
        expect(page.get_by_role('button',name='Added',exact=True)).to_be_disabled()
        page.screenshot(path=str(tmp_path/'refresh-mobile.png'))
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).not_to_be_visible()
        browser.close()


def test_inline_script_does_not_resemble_html_tags():
    # DOMPurify strips an entire script containing HTML-like comparison tokens.
    import re
    from home_design_refresh import render_html
    script = render_html(None).split('<script>', 1)[1].split('</script>', 1)[0]
    assert not re.search(r'<[A-Za-z]', script)
