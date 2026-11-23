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
import os_pages


@pytest.mark.parametrize('change',['none','recipient','quantity','artwork','selected','submission','exhausted'])
def test_unissued_product_permit_recovers_only_the_exact_untouched_blank(blank,monkeypatch,change):
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    plan=product.claim()
    product.finish(plan['key'],plan['token'],'product-select',error='The blank item changed before selection.')
    if change=='recipient':blank.data['recipient']={'name':'Different synthetic destination'}
    if change=='quantity':blank.data['items'][0]['quantity']=2
    if change=='artwork':blank.data['items'][0]['assets']=[{'url':'https://fixture.invalid/unexpected.jpg'}]
    if change=='selected':blank.data['items'][0].update(sku=plan['sku'],attributes={'color':'natural'})
    value=saved()
    if change=='submission':value['submission']={'status':'submitted'}
    if change=='exhausted':value.update(product_readback_recoveries=2,product_readback_recovery_policy=product.READBACK_POLICY)
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,value)
    assert product.recover_readbacks({'id':'fixture-admin'})==int(change=='none')
    if change=='none':
        assert saved()['status']==product.WAITING and not saved().get('product_browser')
        assert product.finish(plan['key'],plan['token'])['status']=='Handoff unavailable'
        with pytest.raises(PermissionError):product.permit(plan['key'],plan['token'],plan['sha256'])
        replacement=product.claim()
        assert replacement['token']!=plan['token'] and not saved()['product_browser']['started']
        assert product.permit(replacement['key'],replacement['token'],replacement['sha256'])=={'permitted':True}
    else:
        assert saved()['status']=='Needs review' and not saved()['product_browser']['started']
        assert product.claim() is None
    assert not blank.writes


@pytest.mark.parametrize('selected',[True,False])
def test_lost_select_acknowledgement_reconciles_without_replaying_click(blank,monkeypatch,selected):
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    plan=product.claim();product.permit(plan['key'],plan['token'],plan['sha256'])
    product.finish(plan['key'],plan['token'],'product-select',error='The expected Prodigi control did not finish loading.')
    if selected:blank.data['items'][0].update(sku=plan['sku'],attributes={'color':'natural'})
    assert product.recover_readbacks({'id':'fixture-admin'})==int(selected)
    assert saved()['status']==(browser.WAITING if selected else 'Needs review')
    assert product.claim() is None and not blank.writes


@pytest.mark.parametrize('reference',os_pages.PRODIGI_REFERENCE_MAPPINGS)
def test_reset_select_creates_empty_slot_then_exact_upload_permit(blank,monkeypatch,reference):
    """Real Select materializes a required asset slot, unlike old fixtures."""
    monkeypatch.setenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','true')
    source=snapshot();source['mapping']=os_pages.prodigi_mapping_for_variant(reference['sports_cave_variant'])
    value=saved();value.update(snapshot=source,fingerprint=prep.digest(source),reset_generation='generation')
    value['reset_authorisation']=dict(generation='generation',order_id=value['order_id'],
        item_id=value['item_id'],assets=[],before=browser.business(blank.data,value['item_id']))
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,value)
    monkeypatch.setattr(browser,'context',lambda _: (blank,lambda _:deepcopy(source),
        lambda _:('https://fixture.invalid/art','fixture'),False))
    plan=product.claim();product.permit(plan['key'],plan['token'],plan['sha256'])
    slot=dict(id='required-slot',printArea='default',status='NotYetDownloaded',pageCount=0,required=True)
    blank.data['items'][0].update(sku=plan['sku'],attributes={'color':plan['colour'].lower()} if plan['colour'] else {},assets=[slot])
    # Recover an already exhausted old-policy receipt without replaying Select.
    value=saved();value.update(status='Needs review',product_readback_recovery_policy='supplier-price-readback-v1',product_readback_recoveries=2)
    value['product_browser']['client_stage']='product-readback'
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,value)
    monkeypatch.setattr(prep,'require_user',lambda _:None)
    assert product.recover_readbacks({'id':'fixture-admin'})==1
    value=saved()
    assert value['product_browser']['reset_empty_slot_created'] is True
    assert value['reset_authorisation']['assets']==[slot]
    assert reset.replacement_allowed(value,blank.data,blank.data['items'][0])
    upload=browser.claim(exact_item_supported=True,reset_supported=True)
    assert upload['selected_empty_product'] is True and not upload.get('replace_artwork')
    assert browser.permit(PRODUCT_KEY,upload['token'],upload['sha256'])=={'permitted':True}
    assert saved()['reset_authorisation']['used_at']
    assert product.recover_readbacks({'id':'fixture-admin'})==0
    assert not blank.writes


@pytest.mark.parametrize('change',['url','status','required','pageCount','extra','duplicate','generation','used','recipient','quantity','shipping'])
def test_reset_slot_recovery_rejects_artwork_and_unrelated_changes(blank,monkeypatch,change):
    value=saved();value['reset_generation']='generation'
    value['reset_authorisation']=dict(generation='generation',order_id=value['order_id'],
        item_id=value['item_id'],assets=[],before=browser.business(blank.data,value['item_id']))
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,value)
    plan=product.claim();product.permit(plan['key'],plan['token'],plan['sha256'])
    slot=dict(id='required-slot',printArea='default',status='NotYetDownloaded',pageCount=0,required=True)
    blank.data['items'][0].update(sku=plan['sku'],attributes={'color':'natural'},assets=[slot])
    if change=='url':slot['url']='https://fixture.invalid/unknown.jpg'
    if change=='status':slot['status']='Downloaded'
    if change=='required':slot['required']=False
    if change=='pageCount':slot['pageCount']=1
    if change=='extra':slot['unknown']=None
    if change=='duplicate':blank.data['items'][0]['assets'].append(deepcopy(slot))
    if change=='recipient':blank.data['recipient']={'name':'Different synthetic destination'}
    if change=='quantity':blank.data['items'][0]['quantity']=2
    if change=='shipping':blank.data['shippingMethod']='Express'
    value=saved()
    if change=='generation':value['reset_generation']='stale'
    if change=='used':value['reset_authorisation']['used_at']='previous'
    proof=deepcopy(value['reset_authorisation'])
    with prep.connect() as conn,conn.cursor() as cur:prep.save(cur,value)
    assert product.finish(plan['key'],plan['token'],'product-readback')['status']=='Needs review'
    assert saved()['reset_authorisation']==proof
    assert not saved()['product_browser'].get('verified') and not blank.writes


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
