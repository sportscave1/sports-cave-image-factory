"""Real header with synthetic counts only; no application imports or live writes."""
import json
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

SOURCE = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf-8')
SIDEBAR = '''<div id="sidebar-host"><section data-testid="stSidebar" style="width:280px;position:fixed;left:0;top:120px">
<div class="st-key-sidebar-row-orders"><div data-testid="stButton"><button><p>Orders</p></button></div></div>
</section></div>'''


def config(**changes):
    return dict(appName='Sports Cave OS', currentRouteKey='orders', navigationEpoch=0,
                revision='synthetic', uploadScope='synthetic', navigationRouteKeys={'Orders':'orders'},
                navigationRouteLabels={'orders':'Orders'}, searchIndex=[], ordersEnabled=True,
                orderStatusUrl='/order-status', notificationsUrl='/notifications', **changes)


def script(value):
    return SOURCE[SOURCE.index('<script>') + 8:SOURCE.rindex('</script>')].replace(
        '__SPORTS_CAVE_TOP_BAR_CONFIG__', json.dumps(value))


@contextmanager
def fixture(value=None, viewport=None, **settings):
    state = dict(count=2, fail=False, calls=0, notification_calls=0)
    state.update(settings)
    initial = value or config()
    html = SOURCE.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__', json.dumps(initial)).replace('<body>', '<body>'+SIDEBAR)
    errors = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport=viewport or {'width':1440, 'height':900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        def respond(route):
            assert route.request.method == 'GET', 'Notification checks must never mutate application data'
            if route.request.url.startswith('http://fixture.test/?'):
                route.fulfill(body=html, content_type='text/html')
            elif route.request.url.endswith('/order-status'):
                state['calls'] += 1
                route.fulfill(status=503 if state['fail'] else 200, json={} if state['fail'] else {
                    'ok':True, 'action_required_count':state['count'], 'badge_label':str(state['count']) if state['count'] else ''})
            elif route.request.url.endswith('/notifications'):
                state['notification_calls'] += 1
                route.fulfill(json={'ok':True, 'notifications':[]})
            else:
                route.fulfill(json={})
        page.route('**/*', respond)
        page.clock.install()
        page.goto('http://fixture.test/?page=orders')
        try:
            yield page, state
            assert not errors
        finally:
            browser.close()


def sidebar_badge(page):
    return page.locator('.st-key-sidebar-row-orders .sc-orders-action-badge')


def test_reconnected_current_page_accepts_reset_epoch_and_new_scope(tmp_path):
    initial = config()
    initial.update(navigationEpoch=1, revision='old-scope')
    with fixture(initial, count=0) as (page, state):
        expect(page.locator('#sports-cave-os-top-bar')).to_have_attribute('data-orders-count','0')
        page.evaluate("window.SportsCaveTopBar.completeNavigation({routeKey:'orders',epoch:1})")
        state['count'] = 2
        page.evaluate(script(config()))
        expect(page.locator('#sports-cave-os-top-bar')).to_have_attribute('data-config-revision','synthetic')
        expect(sidebar_badge(page)).to_have_text('2')
        expect(page.locator('#sc-os-orders-notification-count')).to_have_text('2')
        assert state['calls'] == 2
        assert state['notification_calls'] == 0, 'Activity stays lazy; no extra database traffic'
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('2 orders require action')
        assert state['calls'] == 2, 'Opening immediately reuses the fresh count'
        page.screenshot(path=str(tmp_path/'orders-notification-recovered.png'))


def test_redraw_restores_badges_without_a_new_request_and_counts_clear():
    with fixture() as (page, state):
        expect(sidebar_badge(page)).to_have_text('2')
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('2 orders require action')
        page.evaluate("document.querySelector('.sc-orders-action-badge').remove()")
        expect(sidebar_badge(page)).to_have_text('2')
        # A real sidebar redraw replaces its section inside the stable parent.
        page.evaluate('(html)=>document.querySelector("#sidebar-host").innerHTML=html', SIDEBAR[SIDEBAR.index('<section'):SIDEBAR.rindex('</div>')])
        expect(sidebar_badge(page)).to_have_text('2')
        assert state['calls'] == 1
        state['count'] = 1
        page.clock.fast_forward(31000)
        expect(sidebar_badge(page)).to_have_text('1')
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('1 order requires action')
        state['count'] = 0
        page.clock.fast_forward(31000)
        expect(sidebar_badge(page)).to_have_count(0)
        expect(page.locator('#sc-os-orders-notification-count')).to_have_count(0)
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('No new notifications')
        assert state['calls'] == 3


def test_outage_keeps_last_count_marks_delay_and_recovers():
    with fixture() as (page, state):
        expect(sidebar_badge(page)).to_have_text('2')
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('2 orders require action')
        state['fail'] = True
        page.clock.fast_forward(61000)
        expect(sidebar_badge(page)).to_have_text('2')
        expect(page.locator('#sports-cave-os-top-bar')).to_have_attribute('data-orders-state','delayed')
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('Last known count')
        state['fail'] = False
        state['count'] = 1
        page.clock.fast_forward(31000)
        expect(sidebar_badge(page)).to_have_text('1')
        expect(page.locator('#sports-cave-os-top-bar')).to_have_attribute('data-orders-state','ready')


def test_lower_epoch_cannot_replace_another_route_or_pending_navigation():
    initial = config()
    initial['navigationEpoch'] = 2
    with fixture(initial) as (page, state):
        expect(sidebar_badge(page)).to_have_text('2')
        page.evaluate("window.SportsCaveTopBar.completeNavigation({routeKey:'orders',epoch:2})")
        other = config()
        other.update(currentRouteKey='dashboard', revision='late-other-route')
        page.evaluate(script(other))
        expect(page.locator('#sports-cave-os-top-bar')).to_have_attribute('data-config-revision','synthetic')
        page.evaluate("document.querySelector('#sports-cave-os-top-bar').dataset.pendingRouteKey='dashboard'")
        pending = config()
        pending['revision'] = 'late-pending'
        page.evaluate(script(pending))
        expect(page.locator('#sports-cave-os-top-bar')).to_have_attribute('data-config-revision','synthetic')
        assert state['calls'] == 1


def test_repeated_focus_events_coalesce_and_permissions_clear_count():
    with fixture() as (page, state):
        expect(sidebar_badge(page)).to_have_text('2')
        page.evaluate("() => {for(let n=0;n<50;n++) window.dispatchEvent(new Event('focus'));}")
        assert state['calls'] == 1
        state['count'] = 1
        page.clock.fast_forward(5100)
        page.evaluate("() => {for(let n=0;n<50;n++) window.dispatchEvent(new Event('focus'));}")
        expect(sidebar_badge(page)).to_have_text('1')
        assert state['calls'] == 2
        denied = config()
        denied.update(ordersEnabled=False, revision='no-orders-permission')
        page.evaluate(script(denied))
        expect(sidebar_badge(page)).to_have_count(0)
        expect(page.locator('#sc-os-orders-notification-count')).to_have_count(0)
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('No new notifications')
        assert state['calls'] == 2


def test_initial_outage_does_not_claim_zero_orders():
    with fixture(fail=True) as (page, state):
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('Orders status delayed')
        assert 'No new notifications' not in page.locator('#sc-os-notifications-panel').inner_text()
        state['fail'] = False
        page.clock.fast_forward(31000)
        expect(sidebar_badge(page)).to_have_text('2')
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('2 orders require action')


def test_mobile_bell_count_and_order_reminder_are_visible(tmp_path):
    with fixture(viewport={'width':390, 'height':844}) as (page, state):
        expect(page.locator('#sc-os-orders-notification-count')).to_be_visible()
        expect(page.locator('#sc-os-orders-notification-count')).to_have_text('2')
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('2 orders require action')
        assert state['calls'] == 1
        page.screenshot(path=str(tmp_path/'orders-notification-mobile.png'))
