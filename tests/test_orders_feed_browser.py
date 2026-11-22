"""Real component, synthetic HTTP only. Never touches a live order or account."""
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright,expect
import orders_feed

ROOT=Path(__file__).resolve().parents[1]/'components/orders_prodigi_grid'


def row(number):
    return dict(id=f'allocation:{number}',unit_key=f'unit:{number}',revision=str(number%10)*64,
        cells=dict(order=f'#SC{number}',customer='Synthetic customer',product=f'Synthetic artwork {number}',variant='Black / L',edition=f'#{number:03}/100',shipping='Standard shipping',date='2026-11-22',prodigi='Pending'),
        state=dict(tone='pending',action=''),psd='/synthetic.psd',jpg='',certificate='',
        review=dict(allocation_id=str(number),status='Queued',can_restart=False,preview=f'/preview/{number}.jpg',proof_url=f'/full/{number}.jpg',items=[]))


@contextmanager
def fixture():
    state=dict(rows=[row(n) for n in range(1,98)],fail=False,previews=0,full=0,requests=0)
    errors=[];args=dict(rows=deepcopy(state['rows']),selected=[],active=True,feed=dict(scope='fixture',query='',version=''))
    image=BytesIO();Image.new('RGB',(1000,600),'#aa8833').save(image,format='JPEG');jpg=image.getvalue()
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport=dict(width=1500,height=1000))
        page.on('pageerror',lambda error:errors.append(str(error)))
        def respond(route):
            path=route.request.url.split('fixture.test',1)[-1]
            if path=='/':
                route.fulfill(content_type='text/html',body='''<input id="search" placeholder="Search orders"><iframe style="width:100%;height:900px;border:0" src="/component/index.html"></iframe>''')
            elif path.startswith('/component/'):
                name=path.split('/')[-1].split('?')[0]
                route.fulfill(content_type='text/html' if name.endswith('html') else 'text/javascript',body=(ROOT/name).read_text(encoding='utf-8'))
            elif path=='/api/orders/feed':
                state['requests']+=1
                assert route.request.method=='POST'
                if state['fail']:route.fulfill(status=503,json={'error':'Synthetic failure'});return
                body=route.request.post_data_json
                saved=dict(rows=state['rows'],version=orders_feed.signature([(r['id'],r['revision']) for r in state['rows']]))
                route.fulfill(json={**orders_feed.delta(saved,body['known']), 'delayed':False})
            elif path.startswith('/api/orders-companion/status'):route.fulfill(json={'orders':{}})
            elif path.startswith('/preview/') or path.startswith('/full/'):
                state['previews' if path.startswith('/preview/') else 'full']+=1
                route.fulfill(content_type='image/jpeg',body=jpg)
            else:raise AssertionError('Unexpected fixture request: '+path)
        page.route('**/*',respond);page.goto('http://fixture.test/')
        frame=page.frames[1];frame.wait_for_function("typeof render==='function'")
        def send(value):page.evaluate("value=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args:value},location.origin)",value)
        send(args);expect(frame.locator('tbody tr')).to_have_count(50)
        try:yield page,frame,state,args,send,errors
        finally:browser.close()


def test_new_arrival_keeps_dom_anchor_selection_drawer_search_and_lazy_proof():
    with fixture() as (page,frame,state,args,send,errors):
        page.locator('#search').fill('Keep my draft search')
        frame.locator('tr[data-unit-id="allocation:15"] input').check()
        expect(frame.locator('.drawer')).to_be_visible()
        frame.evaluate("document.querySelector('.scroll').scrollTop=460; document.querySelector('.drawer-body').scrollTop=60; window.preservedRow=document.querySelector('tr[data-unit-id=\"allocation:15\"]')")
        before=frame.evaluate('viewportAnchor()');drawer_scroll=frame.locator('.drawer-body').evaluate('(n)=>n.scrollTop')
        state['rows'].insert(0,row(100))
        frame.evaluate('refreshFeed()')
        assert frame.evaluate('window.preservedRow===document.querySelector(\'tr[data-unit-id="allocation:15"]\')')
        after=frame.evaluate('viewportAnchor()');assert after['id']==before['id'] and abs(after['offset']-before['offset'])<2
        expect(frame.locator('tr[data-unit-id="allocation:15"] input')).to_be_checked()
        assert frame.locator('.drawer-body').evaluate('(n)=>n.scrollTop')==drawer_scroll
        assert page.locator('#search').input_value()=='Keep my draft search' and state['full']==0
        # A late selection acknowledgement from Python still has the old window.
        stale=deepcopy(args);stale['selected']=['allocation:15'];send(stale)
        frame.wait_for_function("args.rows.some(r=>r.id==='allocation:100')")
        assert frame.evaluate('window.preservedRow===document.querySelector(\'tr[data-unit-id="allocation:15"]\')')
        # Simulate only the fragment's authoritative acknowledgement.
        args.update(rows=deepcopy(state['rows']),selected=['allocation:15'])
        args['feed']['version']=orders_feed.signature([(r['id'],r['revision']) for r in state['rows']]);send(args)
        assert frame.evaluate('window.preservedRow===document.querySelector(\'tr[data-unit-id="allocation:15"]\')')
        frame.locator('.proof').click();expect(frame.locator('.zoom-dialog')).to_be_visible()
        expect(frame.locator('.zoom-stage img')).to_be_visible();assert state['full']==1 and not errors


def test_later_page_and_error_recovery_preserve_review_without_loading_screen():
    with fixture() as (_,frame,state,_,_,errors):
        frame.locator('#orders-next-page').click()
        frame.locator('tr[data-unit-id="allocation:60"] input').check()
        state['fail']=True;frame.evaluate('refreshFeed()')
        expect(frame.locator('#orders-update-notice')).to_be_visible()
        expect(frame.locator('tr[data-unit-id="allocation:60"] input')).to_be_checked()
        assert frame.locator('.pagination').inner_text().startswith('51–97')
        state['fail']=False;state['rows'].insert(0,row(100));frame.evaluate('feedRetryAt=0;refreshFeed()')
        expect(frame.locator('#orders-update-notice')).to_have_count(0)
        assert frame.locator('.pagination').inner_text().startswith('51–98')
        expect(frame.locator('tr[data-unit-id="allocation:60"] input')).to_be_checked()
        assert not errors
