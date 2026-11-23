"""Disposable database regressions for the observed multi-edition handoff failures."""
from copy import deepcopy
import pytest
import prodigi_browser as browser
import prodigi_preparation as prep
import prodigi_product_browser as product
import prodigi_reset as reset
import prodigi_sandbox as sandbox
from test_prodigi_browser import handoff, offline, render_url, KEY as SANDBOX_KEY
from test_prodigi_product_browser import blank, saved, KEY as PRODUCT_KEY
from test_prodigi_preparation import store, snapshot
from test_auto_editions_jobs import database


@pytest.mark.parametrize('change',['none','currency','quantity','artwork'])
def test_first_save_reconciles_initial_sibling_prices_without_repeating_upload(handoff,monkeypatch,change):
    _,provider,_=handoff
    sibling={'id':'89','merchantReference':'synthetic-sibling','sku':'different','quantity':1,'assets':[]}
    if change=='currency':sibling['unitPrice']={'amount':'1','currency':'AUD'}
    provider.data['items'].append(sibling)
    plan=browser.claim();browser.permit(SANDBOX_KEY,plan['token'],plan['sha256'])
    provider.artwork('99','88',render_url(),'a'*32)
    sibling.update(unitPrice={'amount':'37.40','currency':'USD'},lineTotal={'amount':'37.40','currency':'USD'})
    if change=='quantity':sibling['quantity']=2
    if change=='artwork':sibling['assets']=[{'url':'unexpected','printArea':'default'}]
    monkeypatch.setattr(browser,'verify_file',lambda *args:True)
    result=browser.finish(SANDBOX_KEY,plan['token'])
    assert result['status']==('Needs QA' if change=='none' else 'Needs review')
    assert len(provider.writes)==1
    assert bool(sandbox.list_tests()[0]['browser'].get('verified'))==(change=='none')


@pytest.mark.parametrize('stale',[False,True])
def test_authorised_blank_selection_advances_only_the_same_unused_reset(blank,monkeypatch,stale):
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    value=saved();value['reset_generation']='generation'
    value['reset_authorisation']={'generation':'old' if stale else 'generation',
        'order_id':value['order_id'],'item_id':value['item_id'],
        'assets':deepcopy(blank.data['items'][0].get('assets') or []),
        'before':browser.business(blank.data,value['item_id'])}
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,value)
    plan=product.claim();product.permit(plan['key'],plan['token'],plan['sha256'])
    blank.data['items'][0].update(sku=plan['sku'],attributes={'color':'natural'})
    result=product.finish(plan['key'],plan['token'])
    assert result['status']==('Needs review' if stale else browser.WAITING)
    assert bool(saved()['product_browser'].get('verified')) is not stale
    if not stale:
        assert reset.replacement_allowed(saved(),blank.data,blank.data['items'][0])
    assert not blank.writes


@pytest.mark.parametrize('sibling_verified',[True,False])
@pytest.mark.parametrize('recover',[True,False])
def test_multi_item_save_uses_only_the_siblings_own_verified_receipt(handoff,monkeypatch,sibling_verified,recover):
    _,provider,value=handoff
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    target=deepcopy(value['snapshot'])
    sibling_source=deepcopy(target);sibling_source['identity']['line_id']='sibling-line'
    sibling={'id':'89','merchantReference':'sibling-line','sku':target['mapping']['prodigi_code'],
        'quantity':1,'attributes':{'color':target['mapping']['prodigi_frame_colour'].lower()},'assets':[],'sizing':'fillPrintArea'}
    provider.data['items'].append(sibling)
    value.update(environment='live',browser_requested=True)
    with prep.connect() as conn,conn.cursor() as cur:
        cur.execute("UPDATE app_settings SET value=jsonb_set(value,'{hidden}','true'::jsonb) WHERE key=%s",(SANDBOX_KEY,))
        prep.save(cur,value)
    monkeypatch.setattr(browser,'context',lambda _: (provider,lambda aid:deepcopy(target if aid==1 else sibling_source),
        lambda _:('https://fixture.invalid/art','a'*32),False))
    plan=browser.claim(exact_item_supported=True)
    browser.permit('prodigi_prepare:1',plan['token'],plan['sha256'])
    provider.artwork('99','88',render_url(),'a'*32)
    sibling.update(assets=[{'url':render_url(image='https://live-services.pwinty.com/sibling-original'),'printArea':'default'}],sizing='fitPrintArea')
    proof={'allocation_id':2,'order_id':'99','item_id':'89','snapshot':sibling_source,
        'browser':{'started':True,'verified':sibling_verified,'filename':'sibling.jpg',
            'original_sha256':sibling_source['output']['sha256'],'original_asset_id':'sibling-asset'}}
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,proof)
    monkeypatch.setattr(browser,'verify_original',lambda provider,url,filename,*args:
        ('sibling-asset' if filename=='sibling.jpg' else 'target-asset',True))
    if recover:
        current=prep.read(1);current.update(status='Needs review')
        current['browser'].update(last_stage='save',readback_changed_fields=['items[1].assets','items[1].sizing'])
        with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,current)
        monkeypatch.setattr(prep,'require_user',lambda _:None)
        assert browser.recover_saved_uploads({'id':'fixture-admin'})==int(sibling_verified)
        result=prep.read(1)
        assert result['saved_readback_recoveries']==1
        assert browser.recover_saved_uploads({'id':'fixture-admin'})==0
    else:result=browser.finish('prodigi_prepare:1',plan['token'])
    assert result['status']==('Needs QA' if sibling_verified else 'Needs review')
    assert len(provider.writes)==1
    saved=prep.read(1)
    assert bool(saved['browser'].get('verified')) is sibling_verified
    if sibling_verified:assert saved['browser']['verified_sibling_items']==['89']
