from copy import deepcopy
from auto_editions_asset_audit import reconcile
from auto_editions_cloud import DropboxAssets


def fixture():
    digest='a'*64
    receipts=[dict(file_id='id:'+str(n),name=f'number-{n}.png',revision='b1',bytes=100) for n in range(1,4)]
    records=[dict(hash=digest,mapped=True,receipts={'assets':receipts})]
    entries=[dict(id=r['file_id'],name=r['name'],rev=r['revision'],size=r['bytes'],
                  path_display=DropboxAssets.path(digest,r['name'])) for r in receipts]
    return records,entries


def test_complete_inventory_read_only_flags_orphan_mismatch_and_missing():
    records,entries=fixture();entries.pop();entries[0]['rev']='b2'
    entries.append({**entries[1],'id':'id:orphan'})
    before=deepcopy((records,entries))
    result=reconcile(records,entries,complete=True)
    assert result['read_only'] and len(result['issues'])==3
    assert {'id:1','id:3','id:orphan'}=={i['file_id'] for i in result['issues']}
    assert (records,entries)==before


def test_partial_inventory_never_infers_missing_and_pages_are_bounded():
    records,entries=fixture()
    assert not reconcile(records,entries[:1])['issues']
    assert reconcile(records,entries,complete=True,limit=1)['next_offset']==1
    assert not reconcile(records,entries,complete=True,limit=1)['issues']
    assert not reconcile(records,entries,complete=True,offset=2,limit=1)['issues']


def test_prepared_pngs_and_source_psds_never_become_mapping_candidates():
    records,entries=fixture();records[0]['mapped']=False
    entries.append(dict(id='id:source',path_display='/Originals/Art.psd'))
    result=reconcile(records,entries,complete=True)
    assert len(result['issues'])==2
    assert 'path_display' not in str(result)


def test_legacy_receipt_size_gap_is_not_reported_as_changed_bytes():
    from auto_editions_discovery import inspect_prepared_receipts
    records,entries=fixture()
    del records[0]['receipts']['assets'][0]['bytes']
    report=reconcile(records,entries,complete=True)
    assert len(report['issues'])==1 and 'no size evidence' in report['issues'][0]['reason']
    read=lambda fid:next(e for e in entries if e['id']==fid)
    report=inspect_prepared_receipts(records,read)
    assert len(report['issues'])==1 and 'no size evidence' in report['issues'][0]['reason']
