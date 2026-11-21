"""Real browser controller, intercepted synthetic traffic only."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def test_initial_failure_recovery_remount_and_identity(tmp_path):
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    config = dict(appName='Sports Cave OS', appSubtitle='Operations System',
                  uploadScope='alice-v1', revision='alice-v1', staffUploadProgress=True,
                  companionQueuesEnabled=True, currentRouteKey='dashboard',
                  navigationRouteKeys={}, navigationRouteLabels={}, searchIndex=[])
    script = source[source.index('<script>')+8:source.rindex('</script>')].replace(
        '__SPORTS_CAVE_TOP_BAR_CONFIG__', json.dumps(config))
    html = source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__', json.dumps(config))
    status = dict(fail=True, requests=0)
    payload = dict(online=True, display_state='ready', jobs=[], queues=dict(
        upload=dict(display=True, enabled=True, waiting=0),
        design=dict(enabled=True, waiting=0, jobs=[dict(id='a',title='Alice design',state='running',label='Generating',percent=40)]),
        ads=dict(enabled=True, waiting=0, online=True, jobs=[])))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport=dict(width=390, height=844))
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def route(request):
                url = request.request.url
                if url == 'http://fixture.test/':
                    request.fulfill(body=html, content_type='text/html')
                elif '/staff-product-uploads/status' in url:
                    status['requests'] += 1
                    request.fulfill(status=503 if status['fail'] else 200,
                                    json={'error':'synthetic outage'} if status['fail'] else payload)
                else:
                    request.fulfill(json={})
            page.route('**/*', route)
            page.clock.install()
            page.goto('http://fixture.test/')
            for name in ('design','upload','ads'):
                expect(page.locator('#sc-os-'+name+'-card')).to_be_visible()
            expect(page.locator('#sc-os-design-stage')).to_have_text('Status delayed · retrying')
            status['fail'] = False
            page.clock.fast_forward(4100)
            expect(page.locator('#sc-os-design-title')).to_have_text('Alice design')
            assert status['requests'] == 2
            # Older completed upload with unfinished ads cannot pin Uploads.
            payload['jobs']=[dict(id='greek',title='Greek Freak',stage=6,label='Published and PSD mapped',percent=100,
                updated_at='2026-11-18T05:27:00Z',ad=dict(active=True,label='Waiting for catalogue')),
                dict(id='new',title='True Blue',stage=6,label='Published and PSD mapped',percent=100,updated_at='2026-11-18T21:16:00Z')]
            payload['queues']['ads']['jobs']=[dict(id='greek-ad',title='Greek Freak ad',state='running',label='Waiting for catalogue',percent=40)]
            page.clock.fast_forward(2100)
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('True Blue')
            expect(page.locator('#sc-os-ads-title')).to_have_text('Greek Freak ad')
            payload['jobs'].append(dict(id='current',title='Bound in Gold',stage=2,label='Generating mockups',percent=34))
            page.clock.fast_forward(2100)
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Bound in Gold')
            payload['jobs'][-1].update(stage=6,label='Published and PSD mapped',percent=100,updated_at='2026-11-19T03:00:00Z')
            page.clock.fast_forward(2100)
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Bound in Gold')
            expect(page.locator('#sc-os-ads-title')).to_have_text('Greek Freak ad')
            status['fail'] = True
            # Reinstall exactly as a Streamlit iframe rerun does.
            page.evaluate(script)
            expect(page.locator('#sc-os-design-title')).to_have_text('Alice design')
            expect(page.locator('#sc-os-design-card')).to_be_visible()
            expect(page.locator('#sc-os-design-stage')).to_have_text('Status delayed · retrying')
            count = status['requests']
            page.clock.fast_forward(4100)
            expect(page.locator('#sc-os-design-stage')).to_have_text('Status delayed · retrying')
            assert status['requests'] == count + 1, 'old controller must not schedule polls'
            page.evaluate('(config)=>window.SportsCaveTopBar.install(config)',
                          {**config, 'uploadScope':'bob-v1', 'revision':'bob-v1', 'companionQueuesEnabled':False})
            expect(page.locator('#sc-os-design-card')).to_be_hidden()
            assert 'Alice design' not in page.locator('#sports-cave-os-top-bar').text_content()
            expect(page.locator('#sc-os-upload-card')).to_be_visible()
            assert not errors
            page.screenshot(path=str(tmp_path/'header-outage-mobile.png'))
        finally:
            browser.close()


def test_header_read_deadline_and_planner_outage_keep_timer():
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    config = dict(appName='Sports Cave OS', revision='timer', navigationRouteLabels={},
                  navigationRouteKeys={}, searchIndex=[], dailyPlannerEnabled=True,
                  dailyPlannerTimerScope='fixture', dailyPlannerStatusUrl='/planner',
                  currentRouteKey='dashboard')
    state = dict(mode='ready', calls=0)
    timer = dict(id='one', task='Keep visible', status='paused', remaining_seconds=120)
    html = source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__', json.dumps(config))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page()
            def respond(route):
                if route.request.url == 'http://fixture.test/':
                    route.fulfill(body=html, content_type='text/html')
                elif route.request.url.endswith('/planner'):
                    state['calls'] += 1
                    route.fulfill(json=dict(timer=timer,events=[]) if state['mode']=='ready'
                                  else dict(available=False, events=[]))
                else:
                    route.fulfill(json={})
            page.route('**/*', respond)
            page.clock.install()
            page.goto('http://fixture.test/')
            expect(page.locator('#sc-os-planner-timer-pill')).to_be_visible()
            state['mode'] = 'outage'
            page.clock.fast_forward(31000)
            expect(page.locator('#sc-os-planner-timer-pill')).to_contain_text('Keep visible')
            assert state['calls'] == 2
            # A hanging transport rejects when the shared read deadline aborts it.
            page.evaluate('''() => {
                window.fixtureFetch=window.fetch;
                window.fetch=(url,options)=>String(url).endsWith('/planner')
                  ? new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('timeout','AbortError'))))
                  : window.fixtureFetch(url,options);
            }''')
            page.clock.fast_forward(31000)
            page.clock.fast_forward(8100)
            expect(page.locator('#sc-os-planner-timer-pill')).to_contain_text('Keep visible')
            page.evaluate('window.fetch=window.fixtureFetch')
            state['mode']='ready'
            timer['task']='Recovered'
            page.clock.fast_forward(31000)
            expect(page.locator('#sc-os-planner-timer-pill')).to_contain_text('Recovered')
        finally:
            browser.close()
