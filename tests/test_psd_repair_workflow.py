"""Synthetic regressions for exact PSD roles, guarded repair and Orders feedback."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import pytest
from tests.test_auto_editions_repair import broken,database,store,pglite_database,PID,asset
import auto_editions_repair as repair
from orders_artwork_repair import projection


def test_reviewed_duplicate_roles_require_exact_source_ids_bounds_and_editability(monkeypatch,tmp_path):
    import auto_editions_role_evidence as evidence
    from auto_editions_onboarding import detect_roles
    from tests.test_auto_editions_onboarding import inspection
    data=inspection();source=dict(product_gid=PID,file_id='id:fixture',revision='a',content_hash='a'*64)
    for i,layer in enumerate(data['layers'],1):layer['layer_id']=i
    obsolete=deepcopy(data['layers']);obsolete[0]['layer_id']=3;obsolete[1]['layer_id']=4
    data['layers']+=obsolete
    selected=dict(source=source,exact_role_ids=True,source_dimensions=[2835,2004])
    for role,layer in zip(('number','plaque'),data['layers']):
        selected[role]=dict(name=layer['path'][0]['name'],layer_id=layer['layer_id'],bounds_px=layer['bounds_px'],kind=layer['kind'])
    registry=tmp_path/'roles.json';registry.write_text(json.dumps(dict(resolutions=[selected])))
    monkeypatch.setattr(evidence,'REGISTRY',registry)
    before=deepcopy(data)
    assert detect_roles(data,100,source=source)['number_layer']=='001 / 100'
    assert data==before
    with pytest.raises(ValueError,match='one visible'):detect_roles(data,100,source={**source,'revision':'changed'})
    data['layers'][0]['bounds_px']=[1,2,3,4]
    with pytest.raises(ValueError,match='evidence changed'):detect_roles(data,100,source=source)
    data=deepcopy(before);data['layers'][0]['editable']=False
    with pytest.raises(ValueError,match='not independently editable'):detect_roles(data,100,source=source)


def test_known_layer_repair_reenters_native_queue_without_codex(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    assets=SimpleNamespace(token='synthetic',integration=SimpleNamespace(psd_open_metadata=lambda *a,**k:asset()))
    with patch('auto_editions_runtime.storage',return_value=assets),patch('auto_editions_role_evidence.resolution',return_value={'exact_role_ids':True}),patch('worker_health_queue.submit') as submit:
        repair.run_one(d.connect)
    assert submit.call_args.kwargs['repair_confirmed'] is True
    with d.connect() as c,c.cursor() as cur:detail=repair.latest(cur,PID)['detail']
    assert detail['state']=='Waiting' and detail['role_repair_revision'] and repair.claim(d.connect) is None


def test_failed_receipt_keeps_specific_reason_for_orders(broken):
    d,sql=broken;repair.request(d.connect,PID,'admin',str(uuid.uuid4()))
    with d.connect() as c,c.cursor() as cur:record=repair.latest(cur,PID)
    repair.checkpoint(d.connect,record,'Codex queued',prompt='scoped synthetic repair')
    receipt=repair.claim(d.connect)
    repair.returned(d.connect,PID,receipt['request_id'],receipt['handoff_token'],False,'Local repair tools are unavailable.')
    with d.connect() as c,c.cursor() as cur:detail=repair.latest(cur,PID)['detail']
    assert detail['state']=='Needs help' and detail['message']=='Local repair tools are unavailable.'


def test_invalid_allocation_is_never_admitted(broken):
    d,sql=broken
    sql.execute("INSERT INTO edition_orders VALUES (7,%s,'cancelled',false,true,NULL)",(PID,))
    with pytest.raises(ValueError,match='Allocation'):repair.request(d.connect,PID,'admin',str(uuid.uuid4()),7)


def test_orders_reads_repair_journal_in_batch_without_writing(broken):
    from orders_artwork_repair import batch
    d,sql=broken
    sql.execute("INSERT INTO edition_orders VALUES (7,%s,'assigned',true,true,NULL),(8,%s,'assigned',true,true,NULL)",(PID,PID))
    initial=batch(d.connect,[7,8])
    assert set(initial)=={'7','8'} and all(r['repairable'] for r in initial.values())
    repair.request(d.connect,PID,'admin',str(uuid.uuid4()),7)
    active=batch(d.connect,[7,8])
    assert all(r['active'] and not r['repairable'] for r in active.values())
    assert all('Exactly one' in r['cause'] for r in active.values())


def test_orders_exposes_psd_cause_and_queue_without_supplier_reset():
    import orders_prodigi_grid as grid
    raw=dict(id=7,product_gid=PID,status='assigned',allocation_valid=True,identity_enforced=True,
             preparation_status='Needs PSD Repair',reason='Two number layers require diagnosis.')
    artwork=projection(raw)
    view=grid.review(dict(status='Needs review',_artwork=artwork),dict(edition_order_id=7),'')
    assert view['status']=='PSD repair' and view['artwork']['repairable'] and not view['can_reset']
    assert 'Two number layers' in view['message']
    complete=grid.review(dict(status='Complete',_artwork=artwork),dict(edition_order_id=7),'')
    assert complete['status']=='Complete' and not complete['artwork']['repairable']
    assert grid.latest_update(['2026-11-23T01:00:00Z','2026-11-23 02:00:00+00:00'])=='2026-11-23 02:00:00+00:00'
    raw['repair_detail']=dict(state='Waiting',message='Verified PSD repair queued.')
    artwork=projection(raw)
    assert artwork['active'] and not artwork['repairable']
    raw['invalidated_at']='fixture'
    assert not projection(raw)['repairable'] and not projection(raw)['active']
