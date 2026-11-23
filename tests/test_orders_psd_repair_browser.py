"""One click queues exact synthetic units; failed posts retain idempotency."""
from copy import deepcopy
from playwright.sync_api import expect
from tests.test_orders_feed_browser import fixture


def repair_row(row,product):
    row['review'].update(status='PSD repair',can_restart=False,artwork=dict(product_gid=product,
        allocation_id=int(row['review']['allocation_id']),repairable=True,active=False,
        message='Exactly one editable number is required.'))


def test_both_row_buttons_submit_without_a_status_page_or_second_click():
    with fixture() as (page,frame,state,args,send,errors):
        frame.evaluate("crypto.randomUUID=()=>`00000000-0000-4000-8000-${String(Math.floor(Math.random()*1e10)).padStart(12,'0')}`")
        requests=[]
        def queued(route):
            body=route.request.post_data_json;requests.append(body)
            route.fulfill(status=202,json=dict(ok=True,repair=dict(state='Queued',message='PSD repair queued.',
                request_id=body['request_id'],changed_at='2026-11-23T00:00:00+00:00')))
        page.route('**/api/auto-editions/repair',queued)
        for i in range(2):repair_row(args['rows'][i],'gid://shopify/Product/'+str(i+100))
        send(args)
        for i in range(2):
            row=frame.locator('tr[data-unit-id="allocation:'+str(i+1)+'"]')
            row.get_by_role('button',name='PSD repair',exact=True).click()
            expect(row.get_by_role('button',name='PSD repairing',exact=True)).to_be_disabled()
        assert len(requests)==2 and [r['allocation_id'] for r in requests]==[1,2]
        assert len({r['product_gid'] for r in requests})==2 and len({r['request_id'] for r in requests})==2
        assert page.url=='http://fixture.test/' and not errors
        expect(frame.get_by_role('status')).to_contain_text('PSD repair queued.')


def test_failure_is_visible_below_checklist_and_retry_reuses_request_id():
    with fixture() as (page,frame,state,args,send,errors):
        frame.evaluate("crypto.randomUUID=()=>`00000000-0000-4000-8000-${String(Math.floor(Math.random()*1e10)).padStart(12,'0')}`")
        requests=[]
        def unavailable(route):
            requests.append(route.request.post_data_json)
            route.fulfill(status=503,json={'error':'Synthetic repair connection unavailable.'})
        page.route('**/api/auto-editions/repair',unavailable)
        repair_row(args['rows'][0],'gid://shopify/Product/100');send(args)
        button=frame.locator('tr[data-unit-id="allocation:1"]').get_by_role('button',name='PSD repair',exact=True)
        button.click()
        expect(frame.get_by_role('status')).to_contain_text('PSD repair was not queued: Synthetic repair connection unavailable.')
        button.click()
        expect(frame.get_by_role('status')).to_contain_text('PSD repair was not queued:')
        assert len(requests)==2 and requests[0]==requests[1] and not errors
