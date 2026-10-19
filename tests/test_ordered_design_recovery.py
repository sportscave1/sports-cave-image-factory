"""Offline checks: real target evidence, parser parity, scope and bounded source IO."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import pytest
import auto_editions_onboarding as onboarding
import auto_editions_role_evidence as roles
import auto_editions_recovery as recovery
from auto_editions_source_limits import check_source,MAX_SOURCE_BYTES,SCRATCH_RESERVE


def resolved_inspection(entry):
    canvas=entry.get('source_dimensions',[3543,2506])
    return dict(document=dict(width_px=canvas[0],height_px=canvas[1]),layers=[
        dict(layer_id=entry['number']['layer_id'],path=[dict(name=entry['number']['name'])],kind='text',
             text=entry['number']['name'],visible=True,editable=True,locked=False,fonts=[dict(installed=True)],
             layout=dict(font='ExactExistingFont'),bounds_px=entry['number']['bounds_px']),
        dict(layer_id=entry['plaque']['layer_id'],path=[dict(name=entry['plaque']['name'])],
             kind=entry['plaque']['kind'],visible=True,bounds_px=entry['plaque']['bounds_px'])])


@pytest.mark.parametrize('index',[0,1,3,4,5,6,7,8])
def test_exact_reviewed_roles_preserve_existing_targets(index):
    entry=json.loads(roles.REGISTRY.read_text())['resolutions'][index]
    result=onboarding.detect(resolved_inspection(entry),100,source=entry['source'])
    assert result['number_layer']==entry['number']['name']
    assert result['plaque_layer']==entry['plaque']['name']


def test_live_native_text_bounds_override_stale_cached_preview():
    data=json.loads(Path('tests/fixtures/ordered_messi_native_inspection.json').read_text())
    entry=json.loads(roles.REGISTRY.read_text())['resolutions'][1]
    result=onboarding.detect(data,100,source=entry['source'])
    assert result['number_bounds']==[1523,2301,2015,2347]
    assert result['font']=='Cinzel-Medium' and result['number_layer']=='No. 001 / 100'


@pytest.mark.parametrize('change',['source','revision','layer_id','bounds','duplicate','second_number'])
def test_changed_or_ambiguous_target_stays_blocked(change):
    entry=json.loads(roles.REGISTRY.read_text())['resolutions'][1];source=deepcopy(entry['source']);data=resolved_inspection(entry)
    if change=='source':source['content_hash']='a'*64
    if change=='revision':source['revision']='b1'
    if change=='layer_id':data['layers'][1]['layer_id']+=1
    if change=='bounds':data['layers'][1]['bounds_px']=[0,0,3000,2400]
    if change=='duplicate':data['layers'].append(deepcopy(data['layers'][1]))
    if change=='second_number':
        second=deepcopy(data['layers'][0]);second['text']='#054/100';second['path']=[dict(name='#054/100')];data['layers'].append(second)
    with pytest.raises(ValueError):onboarding.detect(data,100,source=source)


@pytest.mark.parametrize('text',['No. 001 / 100','no. 001 of 100','  EDITION No. 001 / 100  ','#093/100','001 / 100'])
def test_number_prefix_and_digit_width_preserved(text):
    m=onboarding.NUMBER.fullmatch(text)
    assert m and m[2]==('001' if '001' in text else '093')
    replaced=m[1]+'100'+m[3]+m[4]+m[5]
    assert replaced==text.replace(m[2],'100',1)


def test_source_size_and_disk_headroom(tmp_path):
    with patch('auto_editions_source_limits.shutil.disk_usage') as usage:
        usage.return_value.free=MAX_SOURCE_BYTES*3+SCRATCH_RESERVE
        check_source(1840444389,tmp_path)
        with pytest.raises(ValueError):check_source(MAX_SOURCE_BYTES+1,tmp_path)
        usage.return_value.free=0
        with pytest.raises(ValueError):check_source(1840444389,tmp_path)


def test_recovery_scope_and_roles_are_exact():
    scope=recovery.ordered_scope();assert len(scope)==163
    assert scope['gid://shopify/Product/8116473790771']==231
    assert 'gid://shopify/Product/10063507194163' not in scope
    entry=json.loads(roles.REGISTRY.read_text())['resolutions'][0]
    row=dict(product_gid=entry['source']['product_gid'],status='Needs PSD Repair',priority=8,source=entry['source'],dropbox_file_id=entry['source']['file_id'],reason='A unique recognised collector plaque is required; manual role review needed.')
    decision=recovery.classify(row,dict(policies=[],memberships=[],default_group=''))
    assert decision['action']=='retry_roles' and decision['max_attempts']==1
    row['source']={**row['source'],'content_hash':'a'*64}
    assert recovery.classify(row,dict(policies=[],memberships=[],default_group=''))['action'] is None


def test_role_resolution_does_not_retry_unfixed_font_or_format():
    entry=json.loads(roles.REGISTRY.read_text())['resolutions'][0]
    for reason in ('The exact edition-number font is unavailable.','Existing number formatting cannot hold the full edition range unchanged.'):
        row=dict(product_gid=entry['source']['product_gid'],status='Needs PSD Repair',priority=8,source=entry['source'],dropbox_file_id=entry['source']['file_id'],reason=reason)
        assert recovery.classify(row,dict(policies=[],memberships=[],default_group=''))['action'] is None


def test_large_source_shared_fix_is_bounded_and_not_package_retry():
    source=dict(product_gid='gid://shopify/Product/1',file_id='id:original',revision='a1',content_hash='a'*64)
    row=dict(product_gid=source['product_gid'],status='Blocked',priority=8,source=source,dropbox_file_id=source['file_id'],reason='PSD transfer failed: Source exceeds the preparation transfer limit.',inventory_metadata={'size':1840444389})
    cfg=dict(policies=[],memberships=[],default_group='')
    assert recovery.classify(row,cfg)['action']=='retry'
    assert recovery.classify({**row,'inventory_metadata':{'size':MAX_SOURCE_BYTES+1}},cfg)['action'] is None
    assert recovery.classify({**row,'reason':'Preparation failed: Prepared package exceeds the cloud transfer limit.'},cfg)['action'] is None


def test_transparent_artwork_is_reported_and_never_flattened(tmp_path):
    from PIL import Image
    import auto_editions as ae
    from tests.test_auto_editions import package
    manifest=package(tmp_path)
    path=tmp_path/'master.png'
    Image.new('RGBA',(200,100),(10,20,30,99)).save(path)
    manifest['master']['sha256']=ae.file_hash(path)
    before=path.read_bytes()
    with pytest.raises(ValueError,match='approved opaque composition'):
        ae.compose(manifest,tmp_path,1)
    assert path.read_bytes()==before


def healthy_native(monkeypatch):
    from datetime import datetime,timezone
    from worker_health import code_hash
    monkeypatch.setenv('RENDER_GIT_COMMIT','a'*40)
    return dict(seen_at=datetime.now(timezone.utc),payload=dict(state='Idle',protocol=1,
        revision='a'*40,code_hash=code_hash(),checkpoint_pending=False,processor_lock=False,recovery_failures=0))


def test_legacy_native_error_gets_one_current_guarded_attempt(monkeypatch):
    observed=healthy_native(monkeypatch)
    source=dict(product_gid='gid://shopify/Product/1',file_id='id:original',revision='a1',content_hash='a'*64)
    row=dict(product_gid=source['product_gid'],status='Blocked',priority=8,source=source,dropbox_file_id=source['file_id'],reason='Photoshop inspection failed: OSError. Retry after checking Photoshop.')
    cfg=dict(policies=[],memberships=[],default_group='')
    assert recovery.classify(row,cfg)['action'] is None
    decision=recovery.classify(row,cfg,runtime=observed)
    assert decision['action']=='retry_native' and decision['max_attempts']==1
    for k,v in [('state','Recovering'),('code_hash','b'*64),('revision','b'*40),('processor_lock',True),('checkpoint_pending',True),('recovery_failures',1),('protocol',2)]:
        changed=deepcopy(observed);changed['payload'][k]=v
        assert recovery.classify(row,cfg,runtime=changed)['action'] is None
    assert recovery.classify({**row,'priority':0},cfg,runtime=observed)['action'] is None
    assert recovery.classify({**row,'status':'Cloud Ready'},cfg,runtime=observed)['action'] is None
    row['reason']='Existing number formatting cannot hold the full edition range unchanged.'
    assert recovery.classify(row,cfg,runtime=observed)['action'] is None


def test_compact_transport_reassesses_only_pre_fix_historical_failures(monkeypatch):
    from datetime import datetime,timezone
    observed=healthy_native(monkeypatch)
    source=dict(product_gid='gid://shopify/Product/1',file_id='id:original',revision='a1',content_hash='a'*64)
    row=dict(product_gid=source['product_gid'],status='Blocked',priority=8,source=source,dropbox_file_id=source['file_id'],reason='Preparation failed: Prepared package exceeds the cloud transfer limit.. Existing PSD and mapping are preserved.',updated_at=datetime(2026,10,15,tzinfo=timezone.utc))
    assert recovery.classify(row,{},runtime=observed)['action']=='retry_native'
    row['updated_at']=datetime(2026,10,18,tzinfo=timezone.utc)
    assert recovery.classify(row,{},runtime=observed)['action'] is None


def test_queue_contention_does_not_consume_native_budget_and_is_still_capped():
    from datetime import datetime,timezone,timedelta
    now=datetime.now(timezone.utc)
    event=dict(created_at=now-timedelta(minutes=20),detail=dict(accepted=False,transient_admission=True))
    assert recovery.budget([event],1,now)==''
    assert recovery.budget([event]*3,1,now).startswith('Retry limit reached for temporary')
    assert recovery.budget([dict(created_at=now,detail=event['detail'])],1,now)=='Waiting for capped retry backoff.'
    class Busy(Exception):sqlstate='55P03'
    assert recovery.temporary_admission(Busy())
    assert not recovery.temporary_admission(ValueError('Changed source identity'))
