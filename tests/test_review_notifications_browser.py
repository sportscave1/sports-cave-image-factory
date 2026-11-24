from playwright.sync_api import expect
from tests.test_orders_notification_recovery_browser import fixture, config


def review_config():
    return config(reviewsEnabled=True,reviewsScope='fixture-account',reviewStatusUrl='/review-status')


def seen(page,count=0,scope='fixture-account',at=2):
    page.evaluate('detail=>window.dispatchEvent(new CustomEvent("sc-reviews-seen",{detail}))',
                  {'scope':scope,'unread_count':count,'checked_at':at})


def test_count_bell_and_visible_receipt_clear_without_review_click(tmp_path):
    with fixture(review_config(),reviews=3) as (page,state):
        badge=page.locator('.st-key-sidebar-row-reviews .sc-orders-action-badge')
        expect(badge).to_have_text('3')
        expect(page.locator('#sc-os-orders-notification-count')).to_have_text('5')
        page.locator('#sc-os-notifications').click()
        expect(page.locator('#sc-os-notifications-panel')).to_contain_text('3 new reviews')
        seen(page,scope='another-account');expect(badge).to_have_text('3')
        seen(page);expect(badge).to_have_count(0)
        expect(page.locator('#sc-os-orders-notification-count')).to_have_text('2')
        expect(page.locator('#sc-os-notifications-panel')).not_to_contain_text('3 new reviews')
        assert state['review_calls']==1
        page.screenshot(path=str(tmp_path/'review-notification-cleared.png'))


def test_failed_refresh_retains_badge_and_delayed_response_cannot_restore_seen():
    with fixture(review_config(),reviews=2) as (page,state):
        badge=page.locator('.st-key-sidebar-row-reviews .sc-orders-action-badge')
        expect(badge).to_have_text('2')
        state['review_fail']=True;page.clock.fast_forward(31000)
        expect(badge).to_have_text('2')
        state['review_fail']=False;state['review_hold']=True
        page.clock.fast_forward(31000)
        page.wait_for_function('true')
        seen(page,at=3)
        for route in state.get('held_review_routes',[]):
            route.fulfill(json={'ok':True,'unread_count':2,'checked_at':4})
        expect(badge).to_have_count(0)


def test_reviews_only_permission_keeps_shared_poll_and_refreshes_open_list():
    value=review_config();value.update(ordersEnabled=False,currentRouteKey='reviews',
        navigationRouteKeys={'Reviews':'reviews'},navigationRouteLabels={'reviews':'Reviews'})
    with fixture(value,reviews=1) as (page,state):
        expect(page.locator('.st-key-sidebar-row-reviews .sc-orders-action-badge')).to_have_text('1')
        expect(page.locator('#sc-os-orders-notification-count')).to_have_text('1')
        page.evaluate('''() => {
          document.body.insertAdjacentHTML('beforeend','<div class="st-key-reviews-table"></div><div class="st-key-reviews-refresh"><button>Refresh reviews</button></div>');
          window.reviewRefreshes=0;
          document.querySelector('.st-key-reviews-refresh button').onclick=()=>window.reviewRefreshes++;
        }''')
        page.clock.fast_forward(31000)
        page.wait_for_function('window.reviewRefreshes===1')
        page.clock.fast_forward(31000)
        assert page.evaluate('window.reviewRefreshes')==1
        assert state['calls']==0
        assert state['review_calls']==3
