"""Real browser status-delivery baseline with synthetic HTTP; no provider calls."""
import json
import hashlib
from pathlib import Path
from time import perf_counter
from playwright.sync_api import sync_playwright, expect


def run(source_override=None, compact_status=False):
    source = source_override or (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text()
    config = dict(appName='Sports Cave OS', filesEnabled=True, uploadScope='phase1',
                  staffUploadProgress=True, currentRouteKey='dashboard', revision='phase1',
                  searchIndex=[], navigationRouteLabels={}, navigationRouteKeys={})
    html = source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__', json.dumps(config))
    payload = dict(online=True, jobs=[dict(id='upload', title='Synthetic upload', stage=2,
        label='Generating', percent=34, detail='', updated_at='0')], queues=dict(
        upload=dict(enabled=True, waiting=2, display=True),
        design=dict(enabled=True, waiting=1, jobs=[dict(id='design', title='Synthetic design',
            state='running', label='Generating', percent=45, estimated=True)]),
        ads=dict(enabled=True, online=True, waiting=0, jobs=[dict(id='ad', title='Synthetic ad',
            state='running', label='Generating', percent=40)])))
    result = dict(synthetic=True, provider_generation_measured=False, samples=[], requests=0,
                  response_bytes=0, not_modified=0, errors=[])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script("window.phase1LongTasks=[];new PerformanceObserver(list=>window.phase1LongTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true})")
        def respond(route):
            if route.request.url == 'http://fixture.test/':
                route.fulfill(body=html, content_type='text/html')
            elif '/status' in route.request.url:
                result['requests'] += 1
                if compact_status:
                    from types import SimpleNamespace
                    from companion_status_payload import response
                    reply = response(payload, {'id':'synthetic-admin','role':'admin'},
                        SimpleNamespace(headers=route.request.headers), {'Cache-Control':'private, no-store'})
                    result['response_bytes'] += len(reply.body)
                    result['not_modified'] += reply.status_code == 304
                    route.fulfill(status=reply.status_code, body=reply.body, headers=dict(reply.headers))
                else:
                    body = json.dumps(payload)
                    result['response_bytes'] += len(body.encode())
                    route.fulfill(body=body, content_type='application/json')
            else:
                route.fulfill(json={})
        context.route('**/*', respond)
        pages = []
        try:
            for i in range(5):
                page = context.new_page()
                page.on('pageerror', lambda e: result['errors'].append(str(e)))
                started = perf_counter()
                page.goto('http://fixture.test/')
                expect(page.locator('#sc-os-ads-title')).to_have_text('Synthetic ad')
                result['samples'].append(dict(kind='cold_navigation', tabs=i+1, ms=(perf_counter()-started)*1000))
                pages.append(page)
            for trial in range(3):
                label = 'Verified checkpoint ' + str(trial)
                payload['jobs'][0].update(label=label, updated_at=str(trial+1))
                for queue in ('design', 'ads'):
                    payload['queues'][queue]['jobs'][0]['label'] = label
                for page in pages:
                    started = perf_counter()
                    page.evaluate("document.dispatchEvent(new CustomEvent('sc-design-edit-queued'))")
                    for selector in ('#sc-os-staff-upload-stage', '#sc-os-design-stage', '#sc-os-ads-stage'):
                        expect(page.locator(selector)).to_contain_text(label)
                    result['samples'].append(dict(kind='warm_all_three_status_delivery', trial=trial, tabs=5,
                        ms=(perf_counter()-started)*1000))
            # Repeat unchanged reads without resetting the browser's accepted view.
            for page in pages:
                for _ in range(3):
                    prior = result['requests']
                    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
                    page.wait_for_function('true')
                    # Let routed fetch and continuation finish before the next read.
                    expect(page.locator('#sc-os-ads-stage')).to_contain_text(label)
                    for _attempt in range(50):
                        if result['requests'] > prior:
                            break
                        page.wait_for_timeout(10)
                    page.wait_for_timeout(20)
            result['pages'] = []
            for page in pages:
                cdp = context.new_cdp_session(page)
                cdp.send('Performance.enable')
                metrics = {m['name']:m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}
                result['pages'].append(dict(long_tasks_ms=page.evaluate('window.phase1LongTasks'),
                    screenshot_sha256=hashlib.sha256(page.screenshot(animations='disabled')).hexdigest(),
                    js_heap_used_bytes=metrics.get('JSHeapUsedSize'), nodes=metrics.get('Nodes')))
            assert not result['errors']
            return result
        finally:
            browser.close()


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
