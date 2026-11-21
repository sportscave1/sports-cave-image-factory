from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import prodigi_artwork as artwork
import prodigi_preparation as queue
from auto_editions_jobs import Jobs
from test_auto_editions_jobs import database


@pytest.fixture
def cap(database,monkeypatch):
    jobs,sql=database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    monkeypatch.setattr(queue,'connect',jobs.connect)
    from auto_editions_asset_cache import AssetCache
    monkeypatch.setattr('auto_editions_asset_cache.output_assets',AssetCache())
    identity=dict(allocation_id=1,ordinal=1,order_id='test-order',line_id='test-line',number=12,total=100,
                  variant_id='test-variant',source={'product_gid':'test-product'})
    unit=dict(id=1,allocation_index=1,shopify_order_id='test-order',shopify_line_item_id='test-line',
        edition_number=12,edition_total=100,shopify_variant_id='test-variant',shopify_product_gid='test-product',
        allocation_valid=True,identity_enforced=True,status='assigned')
    data=b'synthetic archived image'
    output=dict(file_id='id:test',revision='abcdef123456',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    record=dict(status='Ready',payload={'identity':identity},result={'output':output,'retained':True,'test_only':False})
    monkeypatch.setattr(Jobs,'read_bound',lambda *args:(record,unit))
    link=artwork.issue(dict(allocation_id=1,job_id='f'*64,output=output))
    return SimpleNamespace(token=link.rsplit('/',1)[-1],link=link,sql=sql,record=record,unit=unit,data=data,output=output)


def test_capability_is_one_file_random_hashed_and_bound_to_current_allocation(cap):
    assert len(cap.token)==43 and '/1/' not in cap.link
    cap.sql.execute('SELECT key,value FROM app_settings')
    stored=cap.sql.fetchone()
    assert cap.token not in json.dumps(stored)
    assert artwork.bound(cap.token)['output']==cap.output
    cap.unit['edition_number']=13
    with pytest.raises(ValueError):artwork.bound(cap.token)


def test_expired_missing_cancelled_and_test_outputs_are_unavailable(cap):
    with pytest.raises(ValueError):artwork.bound('not-a-capability')
    cap.unit['cancelled_at']='now'
    with pytest.raises(ValueError):artwork.bound(cap.token)
    cap.unit.pop('cancelled_at');cap.record['result']['test_only']=True
    with pytest.raises(ValueError):artwork.bound(cap.token)
    cap.record['result']['test_only']=False
    cap.sql.execute("UPDATE app_settings SET value=jsonb_set(value,'{expires_at}',%s::jsonb)",
        (json.dumps((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()),))
    with pytest.raises(ValueError):artwork.bound(cap.token)


def test_serving_preserves_exact_bytes_and_no_customer_filename(cap,monkeypatch):
    import auto_editions_runtime
    closed=[]
    response=SimpleNamespace(iter_content=lambda _:iter([cap.data]),close=lambda:closed.append(True))
    assets=SimpleNamespace(verify_output=lambda _:None,output_response=lambda _:(cap.output,response))
    monkeypatch.setattr(auto_editions_runtime,'storage',lambda:assets)
    app=Starlette(routes=[Route('/image/{token}',artwork.serve,methods=['GET','HEAD'])])
    with TestClient(app) as client:
        head=client.head('/image/'+cap.token)
        assert head.status_code==200 and not closed
        result=client.get('/image/'+cap.token)
        assert result.status_code==200 and result.content==cap.data and closed==[True]
        assert result.headers['content-disposition']=='inline; filename="artwork.jpg"'
        assert result.headers['cache-control']=='private, no-store'
        again=client.get('/image/'+cap.token)
        assert again.content==cap.data and closed==[True]  # Verified cached bytes, no second Dropbox fetch.
        assert client.get('/image/'+'x'*43).status_code==404


def test_corrupted_archive_is_never_served(cap,monkeypatch):
    import auto_editions_runtime
    response=SimpleNamespace(iter_content=lambda _:iter([b'wrong']),close=lambda:None)
    assets=SimpleNamespace(verify_output=lambda _:None,output_response=lambda _:(cap.output,response))
    monkeypatch.setattr(auto_editions_runtime,'storage',lambda:assets)
    app=Starlette(routes=[Route('/image/{token}',artwork.serve,methods=['GET'])])
    with TestClient(app) as client:
        result=client.get('/image/'+cap.token)
        assert result.status_code==404 and b'wrong' not in result.content


def test_cancellation_during_transfer_rejects_response(cap,monkeypatch):
    def fetch(value,folder):
        from pathlib import Path
        path=Path(folder)/'artwork.jpg';path.write_bytes(cap.data)
        cap.unit['cancelled_at']='changed-during-transfer'
        return path
    monkeypatch.setattr(artwork,'fetch',fetch)
    app=Starlette(routes=[Route('/image/{token}',artwork.serve,methods=['GET'])])
    with TestClient(app) as client:
        assert client.get('/image/'+cap.token).status_code==404
