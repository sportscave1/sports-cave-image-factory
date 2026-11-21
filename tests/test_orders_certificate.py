from copy import deepcopy
import pytest
from test_auto_editions_jobs import database
from test_prodigi_preparation import store
import orders_certificate as cert


def test_current_certificate_matches_exact_line_number_and_copy(store,monkeypatch):
    with store() as c,c.cursor() as q:
        q.execute('CREATE TABLE edition_orders(id bigint,allocation_valid bool,invalidated_at timestamptz,shopify_order_id text,shopify_line_item_id text,edition_number int,allocation_index int)')
        q.execute("INSERT INTO edition_orders VALUES(1,true,NULL,'gid://shopify/Order/123','gid://shopify/LineItem/456',12,2)")
    rows=[dict(line_item_id='456',edition_number=12,line_item_unit_index=1,pdf_url='https://cdn.shopify.com/wrong.pdf'),
          dict(line_item_id='gid://shopify/LineItem/456',edition_number=12,line_item_unit_index=2,pdf_url='https://cdn.shopify.com/correct.pdf')]
    calls=[]
    def read(order):calls.append(order);return {'certificates':rows}
    monkeypatch.setattr('certificate_engine.read_order_certificate_state',read)
    assert cert.url(1)=='https://cdn.shopify.com/correct.pdf' and calls==['gid://shopify/Order/123']
    rows.append(deepcopy(rows[1]))
    with pytest.raises(ValueError,match='ambiguous'):cert.url(1)
    rows.pop();rows[1]['pdf_url']='https://another.invalid/file.pdf'
    with pytest.raises(ValueError,match='Shopify-hosted'):cert.url(1)
    with store() as c,c.cursor() as q:q.execute('UPDATE edition_orders SET allocation_valid=false')
    calls.clear()
    with pytest.raises(ValueError,match='unavailable'):cert.url(1)
    assert not calls


def test_certificate_route_requires_orders_access_before_resolving(monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    def denied(*a,**k):raise PermissionError('Orders access required')
    monkeypatch.setattr('files_upload_api._request_user',denied)
    monkeypatch.setattr(cert,'url',lambda _:pytest.fail('No customer file lookup before authorisation'))
    client=TestClient(Starlette(routes=[Route('/certificate',cert.open_certificate)]))
    assert client.get('/certificate?allocation_id=1').status_code==403
