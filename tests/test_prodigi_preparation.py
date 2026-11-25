"""Offline supplier boundary, crash reconciliation and durable queue tests."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
import requests

import prodigi_preparation as queue
from prodigi_client import Client, ProdigiError
from test_auto_editions_jobs import database
from pathlib import Path


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *a, **k: pytest.fail('Live network forbidden'))


def snapshot():
    return dict(allocation_id=1, identity=dict(order_id='123', line_id='456', ordinal=1),
        order_reference='#SC123', job_id='f'*64, output=dict(sha256='a'*64, bytes=100),
        mapping=dict(prodigi_code='GLOBAL-CFP-A2', frame='Oak', prodigi_frame_colour='Natural'),
        shipping='Standard', number=12, total=100, product='Synthetic artwork',
        dimensions=[4200,5940],rendered_number=12,rendered_total=100,
        production_evidence={'print_ready':True,'supplier_sku':'GLOBAL-CFP-A2',
            'output':{'dimensions':[4200,5940],'printable_mm':[420,594]}})


def order():
    return dict(id='99', merchantReference='#SC123', status='draft', allowedActions=['update'],
        items=[dict(id='88', merchantReference='456', sku='GLOBAL-CFP-A2', quantity=1,
                    attributes={'color':'natural'}, assets=[])])


def value():
    snap = snapshot()
    return dict(allocation_id=1, order_id='99', item_id='88', snapshot=snap,
        fingerprint=queue.digest(snap), status='Queued', checks={}, history=[])


class Provider:
    def __init__(self):
        self.data = order()
        self.writes = []
        self.timeout = False

    def order(self, key):
        assert key == '99'
        return deepcopy(self.data)

    def find(self, reference):
        return [deepcopy(self.data)]

    def artwork(self, key, item, url, md5):
        self.writes.append((key, item, url, md5))
        self.data['items'][0]['assets'] = [{'printArea':'default','url':url,'status':'complete'}]
        if self.timeout:
            raise ProdigiError('Acknowledgement lost')
        return self.data


@pytest.mark.parametrize('change,reason', [
    (lambda o:o.update(id='100'), 'different order'),
    (lambda o:o.update(status='paused'), 'editable draft'),
    (lambda o:o.update(allowedActions=['resume']), 'editable draft'),
    (lambda o:o.update(merchantReference='wrong'), 'order reference'),
    (lambda o:o['items'][0].update(quantity=2), 'one separately'),
    (lambda o:o['items'][0].update(merchantReference='wrong'), 'line reference'),
    (lambda o:o['items'][0].update(sku='GLOBAL-CFP-A1'), 'SKU'),
    (lambda o:o['items'][0].pop('sku'), 'No Prodigi product'),
    (lambda o:o['items'][0].update(attributes={'color':'black'}), 'frame colour'),
    (lambda o:o['items'][0].update(assets=[{'printArea':'back'}]), 'Multiple print areas'),
    (lambda o:o['items'].append(deepcopy(o['items'][0])), 'ambiguous'),
])
def test_mismatches_never_write(change, reason):
    o = order(); change(o)
    with pytest.raises(ProdigiError, match=reason):
        queue.validate_order(o, snapshot(), '99', '88')


def test_draft_verified_but_edit_acceptance_is_required(monkeypatch):
    monkeypatch.delenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED', raising=False)
    p = Provider(); saved=[]
    result = queue.run(value(), p, lambda _:snapshot(), lambda _:pytest.fail('No artwork transfer before acceptance'),
                       lambda v:saved.append(deepcopy(v)))
    assert result['status'] == 'Awaiting browser upload'
    assert not p.writes


def test_write_intent_precedes_upload_and_readback_never_submits(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED', 'true')
    p = Provider(); saved=[]
    def persist(v):
        saved.append(deepcopy(v))
        if v['status'] == 'Uploading':
            assert not p.writes
    result = queue.run(value(), p, lambda _:snapshot(), lambda _:('https://fixture.invalid/art.jpg','b'*32), persist)
    assert len(p.writes) == 1
    assert saved[0]['write_intent']
    assert result['status'] == 'Needs QA'
    assert result['checks']['artwork_upload']
    assert not result['checks'].get('final_check')
    assert not result['checks'].get('shipping')


def test_timeout_after_supplier_acceptance_reconciles_without_second_patch(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED', 'true')
    p = Provider(); p.timeout=True; saved=[]
    with pytest.raises(ProdigiError):
        queue.run(value(), p, lambda _:snapshot(), lambda _:('https://fixture.invalid/art.jpg','b'*32),
                  lambda v:saved.append(deepcopy(v)))
    assert saved[-1]['write_intent']
    result=queue.run(saved[-1], p, lambda _:snapshot(), lambda _:pytest.fail('No repeated link or upload'), lambda v:None)
    assert len(p.writes) == 1 and result['status'] == 'Needs QA'


def test_unacknowledged_missing_asset_never_retries_write(monkeypatch):
    v=value(); v.update(write_intent=True,url_hash=queue.digest('https://fixture.invalid/old.jpg'))
    p=Provider()
    with pytest.raises(ValueError, match='uncertain'):
        queue.run(v,p,lambda _:snapshot(),lambda _:pytest.fail('No upload'),lambda v:None)
    assert not p.writes


def test_changed_order_during_transfer_blocks_patch(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED', 'true')
    p=Provider()
    def link(_):
        p.data['shippingMethod']='Express'
        return 'https://fixture.invalid/art.jpg','b'*32
    with pytest.raises(ValueError,match='changed during'):
        queue.run(value(),p,lambda _:snapshot(),link,lambda v:None)
    assert not p.writes


def test_changed_allocation_blocks_even_reconciliation():
    v=value(); snap=snapshot(); snap['number']=13
    with pytest.raises(ValueError,match='changed'):
        queue.run(v,Provider(),lambda _:snap,lambda _:pytest.fail('No upload'),lambda v:None)


def test_discovery_matches_existing_only_and_blocks_multiple_matches():
    p=Provider()
    assert queue.discover(snapshot(),p)==('99','88')
    p.find=lambda _: [order(),dict(order(),id='100')]
    with pytest.raises(ValueError,match='one existing'):
        queue.discover(snapshot(),p)


def test_client_has_only_get_and_draft_item_patch_and_redacts_provider_errors(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    calls=[]
    def request(method,url,**kwargs):
        calls.append((method,url,kwargs))
        return SimpleNamespace(status_code=200,json=lambda:{'data':order()})
    client=Client('fixture-key',SimpleNamespace(request=request),mode='sandbox')
    client.order('99');client.artwork('99','88','https://fixture.invalid/art.jpg','b'*32)
    assert [c[0] for c in calls]==['GET','PATCH']
    assert calls[1][2]['json']=={'assets':[{'printArea':'default','url':'https://fixture.invalid/art.jpg','md5Hash':'b'*32}]}
    assert all(c[2]['allow_redirects'] is False for c in calls)
    with pytest.raises(ValueError):client.order('../orders:submit')
    client.transport.request=lambda *a,**k: SimpleNamespace(status_code=401,text='SECRET')
    with pytest.raises(ProdigiError,match='HTTP 401') as error:client.order('99')
    assert 'SECRET' not in str(error.value)


def test_adapter_itself_rejects_artwork_writes_until_both_flags_are_enabled(monkeypatch):
    client=Client('fixture',SimpleNamespace(request=lambda *a,**k:pytest.fail('No provider write')),mode='sandbox')
    monkeypatch.delenv('SPORTS_CAVE_PRODIGI_PREPARE',raising=False)
    monkeypatch.delenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED',raising=False)
    with pytest.raises(ValueError,match='writes are disabled'):
        client.artwork('99','88','https://fixture.invalid/art.jpg','b'*32)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    with pytest.raises(ValueError,match='writes are disabled'):
        client.artwork('99','88','https://fixture.invalid/art.jpg','b'*32)


def test_documented_mode_prefix_is_added_without_rotating_or_crossing_environments():
    live=Client('synthetic-raw-key',SimpleNamespace())
    sandbox=Client('synthetic-sandbox-key',SimpleNamespace(),mode='sandbox')
    assert live.key=='live_synthetic-raw-key' and sandbox.key=='sandbox_synthetic-sandbox-key'
    with pytest.raises(ValueError,match='different environment'):
        Client('sandbox_fixture',SimpleNamespace(),mode='live')
    with pytest.raises(ValueError,match='different environment'):
        Client('live_fixture',SimpleNamespace(),mode='sandbox')


def test_existing_artwork_with_hidden_editor_data_is_not_overwritten(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    provider=Provider()
    provider.data['items'][0]['assets']=[{'printArea':'default','url':'https://fixture.invalid/existing.jpg'}]
    with pytest.raises(ValueError,match='editor data'):
        queue.run(value(),provider,lambda _:snapshot(),lambda _:pytest.fail('No replacement'),lambda v:None)
    assert not provider.writes


@pytest.mark.parametrize('method,path', [
    ('GET','/auth/api/auth/refresh'), ('POST','/auth/api/auth/validate'),
    ('POST','/orders'), ('POST','/orders/99:submit'), ('POST','/orders/99:resume'),
    ('PATCH','/orders/99'), ('GET','https://dashboard.prodigi.com/login'),
])
def test_supplier_client_cannot_reach_login_or_production_actions(method,path):
    client=Client('fixture-key', SimpleNamespace(request=lambda *a,**k:pytest.fail('Forbidden request')))
    with pytest.raises(ValueError,match='Only existing'):
        client.request(method,path)


def test_api_session_has_no_browser_or_provider_cookie_access():
    import http.cookiejar
    client=Client('fixture-key')
    cookie=http.cookiejar.Cookie(0,'session','secret',None,False,'api.prodigi.com',True,False,
        '/',True,True,None,True,None,None,{})
    assert client.transport.cookies.get_policy().set_ok(cookie,None) is False
    assert client.transport.cookies.get_policy().return_ok(cookie,None) is False


def test_normal_dashboard_link_and_companion_login_isolation():
    import ast
    root=Path(__file__).resolve().parents[1]
    source=(root/'os_pages.py').read_text(encoding='utf8')
    tree=ast.parse(source)
    target=next(node for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='PRODIGI_DASHBOARD_URL' for t in node.targets))
    assert ast.literal_eval(target.value)=='https://dashboard.prodigi.com/'
    assert 'connect-sales-channel/shopify?' not in source
    manifest=json.loads((root/'windows-upload-companion/manifest.json').read_text())
    assert not {'cookies','webRequest','declarativeNetRequest'}.intersection(manifest['permissions'])
    assert {host for host in manifest['host_permissions'] if 'prodigi' in host or 'pwinty' in host} == {
        'https://dashboard.prodigi.com/*','https://sandbox-beta-dashboard.pwinty.com/*'}
    supplier_scripts=[script for script in manifest['content_scripts'] if 'prodigi-page.js' in script['js']]
    assert supplier_scripts[0]['matches']==['https://dashboard.prodigi.com/orders/*/detail',
        'https://sandbox-beta-dashboard.pwinty.com/orders/*/detail']
    scripts=[match for content in manifest['content_scripts'] for match in content['matches']]
    assert not any('<all_urls>' in match for match in scripts)
    # The existing sign-in recovery is restricted to this exact supplier host.
    assert [match for match in scripts if '/login' in match] == ['https://dashboard.prodigi.com/login*']
    login_scripts=[content for content in manifest['content_scripts'] if 'https://dashboard.prodigi.com/login*' in content['matches']]
    assert login_scripts[0]['js']==['prodigi-signin-page.js']
    assert {match for match in scripts if 'prodigi' in match or 'pwinty' in match}==set(supplier_scripts[0]['matches'])|{'https://dashboard.prodigi.com/login*'}
    import io,zipfile
    from upload_companion_page import extension_package
    with zipfile.ZipFile(io.BytesIO(extension_package())) as archive:
        assert 'orders-queue.js' in archive.namelist()
        assert 'orders-wake.js' in archive.namelist()
        import re
        imports=re.findall(r"importScripts\('([^']+)'\)",archive.read('worker.js').decode())
        assert set(imports)<=set(archive.namelist())


def test_artwork_transfer_verifies_archived_bytes_before_issuing_durable_link(monkeypatch):
    from hashlib import sha256,md5
    import auto_editions_runtime
    import dropbox_integration
    data=b'fixture production jpg bytes'
    revision='abcdef123456'
    calls=[]
    response=SimpleNamespace(iter_content=lambda _:iter([data]),close=lambda:None)
    sdk=SimpleNamespace(files_get_temporary_link=lambda path:
        (calls.append(path) or SimpleNamespace(link='https://fixture.invalid/revision.jpg')))
    assets=SimpleNamespace(token='fixture',verify_output=lambda _:None,
        output_response=lambda _:(dict(rev=revision),response),
        integration=SimpleNamespace(team_space_client=lambda _:sdk))
    monkeypatch.setattr(auto_editions_runtime,'storage',lambda:assets)
    snap=snapshot();snap['output']=dict(revision=revision,sha256=sha256(data).hexdigest(),bytes=len(data))
    import prodigi_artwork
    monkeypatch.setattr(prodigi_artwork,'issue',lambda saved:
        (calls.append(saved) or 'https://fixture.invalid/revision.jpg'))
    assert queue.artwork_link(snap)==('https://fixture.invalid/revision.jpg',md5(data).hexdigest())
    assert calls==[snap]


def test_desktop_route_requires_pairing_and_accepts_no_external_instructions(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import prodigi_preparation_api as api
    app=Starlette(routes=[Route('/tick',api.tick,methods=['POST'])])
    user_calls=[];queue_calls=[]
    monkeypatch.setattr(api,'desktop',lambda token:user_calls.append(token))
    monkeypatch.setattr(queue,'tick',lambda:queue_calls.append(True))
    monkeypatch.setattr('prodigi_sandbox.tick',lambda:None)
    monkeypatch.setattr('orders_automatic.kick',lambda:None)
    monkeypatch.setattr('prodigi_submission.kick',lambda:None)
    with TestClient(app) as client:
        assert client.post('/tick',json={}).status_code==403
        assert not user_calls and not queue_calls
        headers={'Authorization':'Bearer '+'x'*43}
        assert client.post('/tick',json={'url':'https://fixture.invalid/wrong.jpg'},headers=headers).status_code==409
        assert not queue_calls
        assert client.post('/tick',content='{}',headers=headers).status_code==200
        assert len(queue_calls)==1


def test_non_admin_cannot_prepare_even_when_enabled(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    monkeypatch.setattr(queue,'resolve',lambda _:pytest.fail('Unauthorised allocation read'))
    with pytest.raises(PermissionError):
        queue.request({'id':'fixture','role':'worker'},1,'99','88')


def test_preparation_ui_retains_manual_qa_and_has_no_production_action(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    saved=value();saved.update(status='Needs QA',message='Fixture uploaded; manual QA required.')
    monkeypatch.setattr(queue,'read',lambda _:saved)
    monkeypatch.setattr(queue,'request_failure',lambda _:None)
    script="""
from prodigi_preparation_ui import render
render({'edition_order_id': '1'}, {'id':'fixture','role':'admin'}, answers={})
"""
    app=AppTest.from_string(script).run()
    assert not app.exception
    labels=[button.label for button in app.button]
    assert 'Save QA · ready for manual payment' in labels
    assert not any('submit' in label.lower() or 'release' in label.lower() for label in labels)
    assert app.checkbox[0].value is False


@pytest.fixture
def store(database,monkeypatch):
    jobs,sql=database
    sql.execute('CREATE TABLE app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    monkeypatch.setattr(queue,'connect',jobs.connect)
    monkeypatch.setattr(queue,'require_user',lambda _:None)
    monkeypatch.setattr(queue,'resolve',lambda _:snapshot())
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    return jobs.connect


def test_durable_requests_deduplicate_and_reserve_supplier_item(store,monkeypatch):
    user={'id':'fixture'}
    first=queue.request(user,1,'99','88')
    assert queue.request(user,1,'99','88')==first
    assert len(queue.list_jobs())==1
    with pytest.raises(ValueError,match='another numbered'):
        queue.request(user,2,'99','88')
    with pytest.raises(ValueError,match='already has'):
        queue.request(user,1,'99','89')
    queue.reconcile(user,1)
    assert queue.read(1)['history'][-1]['event']=='reconcile_requested'


def test_real_sql_new_requests_use_browser_even_if_old_api_acceptance_flag_is_set(store,monkeypatch):
    p=Provider(); p.timeout=True
    monkeypatch.setattr(queue,'Client',lambda:p)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    monkeypatch.setattr(queue,'artwork_link',lambda _:('https://fixture.invalid/art.jpg','b'*32))
    queue.request({'id':'fixture'},1,'99','88')
    result=queue.tick()
    assert result['status']=='Awaiting browser upload' and not result.get('write_intent')
    queue.reconcile({'id':'fixture'},1)
    assert queue.read(1)['browser_requested']
    queue.tick()
    assert not p.writes
    assert queue.read(1)['status']=='Awaiting browser upload'


def test_live_api_artwork_patch_is_blocked_even_with_legacy_acceptance_enabled(monkeypatch):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_PREPARE','true')
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    client=Client('synthetic',SimpleNamespace(request=lambda *a,**k:pytest.fail('No live artwork PATCH')))
    with pytest.raises(ProdigiError,match='companion browser'):
        client.artwork('99','88','https://fixture.invalid/art.jpg','b'*32)


def test_automatic_matching_runs_in_companion_and_missing_product_is_diagnosed(store,monkeypatch):
    p=Provider();p.data['items'][0].pop('sku')
    monkeypatch.setattr(queue,'Client',lambda:p)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    queued=queue.request({'id':'fixture'},1)
    assert queued['order_id']=='' and queued['status']=='Queued'
    result=queue.tick()
    assert result['status']=='Awaiting product selection'
    assert queue.read(1)['order_id']=='99' and not p.writes
    assert queue.request({'id':'fixture'},1)['order_id']=='99'


def test_automatic_matching_does_not_reuse_another_allocations_item(store,monkeypatch):
    monkeypatch.setattr(queue,'Client',Provider)
    queue.request({'id':'fixture'},1,'99','88')
    queue.request({'id':'fixture'},2)
    queue.tick()  # First request stops at acceptance without an artwork write.
    queue.tick()  # Second matches the same item and is stopped by the reservation.
    assert queue.read(2)['status']=='Needs review'
    assert 'another numbered allocation' in queue.read(2)['message']
    assert not queue.read(2).get('write_intent')


def test_review_prompt_binds_exact_unit_and_prohibits_login_or_production_changes():
    prompt=queue.review_prompt(value())
    assert '"order_id": "99"' in prompt and '"edition": "12/100"' in prompt
    assert 'paid packing slip' in prompt and 'Do not log out' in prompt
    assert 'submit, resume or release to production' in prompt


def test_qa_requires_every_question_packing_slip_and_download_readback(store,monkeypatch):
    p=Provider(); monkeypatch.setattr(queue,'Client',lambda:p)
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED','true')
    monkeypatch.setattr(queue,'artwork_link',lambda _:('https://fixture.invalid/art.jpg','b'*32))
    queued=queue.request({'id':'fixture'},1,'99','88')
    # Seed the independently tested upload state; this test exercises the QA gate.
    queued.pop('browser_requested')
    with store() as c,c.cursor() as q:queue.save(q,queued)
    queue.tick()
    answers={key:'Yes' for key in queue.CHECKS}
    with pytest.raises(ValueError,match='all Fulfilment'):
        queue.complete_qa({'id':'fixture'},1,answers,False)
    incomplete=dict(answers,shipping='No')
    with pytest.raises(ValueError,match='all Fulfilment'):
        queue.complete_qa({'id':'fixture'},1,incomplete,True)
    queue.complete_qa({'id':'fixture'},1,answers,True)
    assert queue.read(1)['status']=='Ready for manual payment'
    assert p.data['status']=='draft' and len(p.writes)==1


def test_order_shipping_address_reads_identity_bound_nested_rest_and_camel_case():
    address=dict(name='Synthetic Customer',address1='1 Fixture Road',address2='',city='Fixture',province='Michigan',zip='48000',country_code='US',province_code='MI')
    expected=queue.shopify_recipient(dict(raw_payload=dict(id=123,shipping_address=address)), 'gid://shopify/Order/123')
    assert expected['name']=='Synthetic Customer' and expected['address']['countryCode']=='US'
    assert expected['state_aliases']==['Michigan','MI']
    direct=dict(address,countryCodeV2='US',provinceCode='MI')
    assert queue.shopify_recipient(dict(shippingAddress=direct),'123')==expected
    with pytest.raises(ValueError,match='different'):queue.shopify_recipient(dict(raw_payload=dict(id=124,shipping_address=address)),'123')
    with pytest.raises(ValueError,match='unidentified'):queue.shopify_recipient(dict(raw_payload=dict(shipping_address=address)),'123')
    with pytest.raises(ValueError,match='complete'):queue.shopify_recipient(dict(customer_raw=dict(default_address=address)),'123')


def test_empty_recipient_recovery_preserves_verified_artwork_and_rejects_other_changes():
    old=snapshot();old['recipient']=dict(name=None,address=dict(line1=None,countryCode=None))
    fresh=deepcopy(old);fresh['recipient']=queue.shopify_recipient(dict(shipping_address=dict(name='Synthetic Customer',address1='1 Fixture Road',city='Fixture',province='Michigan',zip='48000',country_code='US')),'123')
    value=dict(allocation_id=1,snapshot=old,fingerprint=queue.digest(old),browser=dict(verified=True),history=[])
    changed=deepcopy(fresh);changed['mapping']['prodigi_code']='DIFFERENT'
    with pytest.raises(ValueError,match='changed'):queue.restore_missing_recipient(deepcopy(value),lambda _:changed)
    assert queue.restore_missing_recipient(value,lambda _:fresh)
    assert value['snapshot']==fresh and value['fingerprint']==queue.digest(fresh) and value['browser']['verified']
    assert value['history'][-1]['event']=='missing_shopify_recipient_recovered'
    assert not queue.restore_missing_recipient(value,lambda _:pytest.fail('Never replace a populated address'))


def test_shipping_display_suffix_is_not_an_artwork_or_address_change():
    a=snapshot();a['recipient']={'address':{'line1':'1 Fixture Street'}}
    b=deepcopy(a);b['shipping']='Standard | Synthetic Customer | Fixture'
    assert queue.same_source(a,b)
    v=value();v.update(snapshot=a,fingerprint=queue.digest(a))
    assert queue.source_matches(v,b)
    for key,changed in [('shipping','Express'),('job_id','b'*64),('number',99),
                        ('mapping',{'prodigi_code':'GLOBAL-CFP-A1'}),
                        ('recipient',{'address':{'line1':'2 Different Street'}}),
                        ('output',{'sha256':'b'*64,'bytes':100})]:
        bad=deepcopy(b);bad[key]=changed
        assert not queue.source_matches(v,bad),key
    v['fingerprint']='tampered'
    assert not queue.source_matches(v,b)


def test_shipping_suffix_refresh_does_not_stop_supplier_matching():
    v=value();v['snapshot']['shipping']='Standard | Synthetic Customer | Fixture'
    v['fingerprint']=queue.digest(v['snapshot']);v['browser_requested']=True
    result=queue.run(v,Provider(),lambda _:snapshot(),lambda _:pytest.fail('No API write'),lambda _:None)
    assert result['status']=='Awaiting browser upload'
