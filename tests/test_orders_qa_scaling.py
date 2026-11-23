"""Synthetic final-QA fan-out benchmark; never calls a supplier or real orders."""
from collections import Counter
from copy import deepcopy
import json
import time
import pytest
import requests
import prodigi_dashboard_qa as qa
import prodigi_preparation as prep
import prodigi_submission as submit
from test_prodigi_submission import ready
from test_prodigi_preparation import store
from test_auto_editions_jobs import database


@pytest.mark.parametrize('count',[1,2,5,10])
def test_submission_read_cost_scales_linearly_and_submits_once(store,monkeypatch,count):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('No live network in benchmark'))
    base,snapshot,provider,auth=ready();template=deepcopy(provider.data['items'][0])
    units=[];sources={};items=[];reads=[];source_reads=[]
    for index in range(count):
        aid=index+1;item_id=str(88+index);line=str(456+index)
        snap=deepcopy(snapshot);snap.update(allocation_id=aid,number=12+index);snap['identity']['line_id']=line
        item=deepcopy(template);item.update(id=item_id,merchantReference=line)
        item['assets'][0]['url']='https://fixture.invalid/numbered-'+str(aid)
        value=deepcopy(base);value.update(allocation_id=aid,item_id=item_id,snapshot=snap,
            fingerprint=prep.digest(snap),url_hash=prep.digest(item['assets'][0]['url']))
        units.append(value);sources[aid]=snap;items.append(item)
    provider.data['items']=items
    pinned=qa.pinned_order(provider.data);pinned['shippingMethod']=provider.data.get('shippingMethod')
    for unit in units:unit['dashboard_qa'].update(before=deepcopy(provider.data),validated_order_hash=prep.digest(pinned))
    original=provider.order
    def read_order(oid):reads.append(oid);return original(oid)
    def read_source(aid):source_reads.append(aid);return deepcopy(sources[aid])
    monkeypatch.setattr(provider,'order',read_order)
    monkeypatch.setattr(prep,'resolve',read_source)
    monkeypatch.setattr(prep,'Client',lambda:provider)
    with prep.connect() as conn,conn.cursor() as cur:
        for unit in units:prep.save(cur,unit)
        cur.execute('INSERT INTO app_settings(key,value) VALUES(%s,%s::jsonb)',(submit.SETTING,json.dumps(auth)))
    started=time.perf_counter();submit.tick();elapsed=(time.perf_counter()-started)*1000
    assert provider.submits==['99']
    assert len(reads)==3 and Counter(source_reads)==Counter({aid:2 for aid in sources})
    assert all(prep.read(aid)['status']=='Submitted' for aid in sources)
    print('QA_BENCH '+json.dumps(dict(items=count,supplier_reads=len(reads),source_reads=len(source_reads),submit_count=len(provider.submits),local_elapsed_ms=round(elapsed,2))))
