from copy import deepcopy
import pytest
import requests
import prodigi_full_qa as full
import prodigi_preparation as prep
from prodigi_qa import evaluate
from test_prodigi_sandbox import source,SandboxProvider
import prodigi_sandbox as sandbox


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Live network forbidden'))


def approved(snap,ready=True):
    return dict(policy=full.POLICY,job_id=snap['job_id'],sha256=snap['output']['sha256'],sku=snap['mapping']['prodigi_code'],
        dimensions=snap['dimensions'],number=snap['number'],total=snap['total'],layout_pixel_proofs_verified=True,
        number_verified=True,supplier_asset_validated=True,print_ready=ready,blockers=[] if ready else ['Native PPI below recommendation'],basis='fixture')


def test_print_area_uses_real_supplier_dimensions_and_native_resolution():
    area,dpi=full.print_area({'printAreas':[{'name':'default','widthMm':420,'heightMm':594,'recommendedDpi':300}]},[11340,8016])
    assert area==[594,420] and dpi==300
    assert min(n*25.4/mm for n,mm in zip([2835,2004],area))<122
    with pytest.raises(ValueError,match='dimensions'):
        full.print_area({'printAreas':[{'name':'default'}]},[100,80])


def test_live_native_preflight_blocks_before_any_artwork_upload(monkeypatch):
    from types import SimpleNamespace
    snap=source();job={'id':snap['job_id'],'manifest':{'source_dimensions':[2835,2004]}}
    monkeypatch.setattr('auto_editions_runtime.job_for',lambda _: (job,None))
    provider=SimpleNamespace(catalogue=lambda _: {'printAreas':[{'name':'default','widthMm':420,'heightMm':594,'recommendedDpi':300}]})
    with pytest.raises(ValueError,match='No live artwork was uploaded'):full.native_gate(snap,provider)
    job['manifest']['source_dimensions']=[7016,9933]
    assert full.native_gate(snap,provider) is None
    job['id']='new-current-master'
    with pytest.raises(prep.MissingJPG):full.native_gate(snap,provider)


@pytest.mark.parametrize('field,value',[('sha256','other'),('job_id','other'),('sku','other'),('number',99),('dimensions',[1,2])])
def test_production_approval_cannot_move_to_different_file_or_edition(field,value):
    snap=source();a=approved(snap);a[field]=value
    assert not full.approval_matches(a,snap)


def test_quality_warning_does_not_hide_successful_independent_checks():
    snap=source();snap.update(production_evidence={},draft_print_approval=approved(snap,False),draft_full_fit_verified=True,certificate_url='https://fixture/cert.pdf')
    p=SandboxProvider();p.create_draft(sandbox.payload(sandbox.adapted(snap,'SC-SANDBOX-fixture',snap['recipient'])),'fixture')
    o=p.data;o.update(recipient=deepcopy(snap['recipient']),shippingMethod=snap['shipping'],packingSlip={'url':snap['certificate_url'],'status':'ready'})
    item=o['items'][0];item['assets']=[{'printArea':'default','url':'https://fixture/art','status':'complete'}]
    qa=evaluate(snap,o,item,prep.digest('https://fixture/art'))
    assert all(qa['checks'][k] for k in ('artwork_upload','size','frame','shipping','certificate','packing_slip','edition_number','sent_to_production'))
    assert not qa['checks']['production_approval'] and not qa['checks']['final_check']


def test_colour_evidence_blocks_missing_invalid_profiles_without_guessing():
    from PIL import ImageCms
    for value in (b'',b'invalid-profile'):
        digest,blocker=full.colour_evidence(value)
        assert digest is None and 'verified colour policy' in blocker
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    digest,blocker=full.colour_evidence(profile)
    assert len(digest)==64 and blocker is None


@pytest.fixture
def pipeline(monkeypatch):
    from test_prodigi_sandbox import source
    snap=source();snap['production_evidence']={};p=SandboxProvider();p.create_draft(sandbox.payload(sandbox.adapted(snap,'SC-SANDBOX-fixture',snap['recipient'])),'fixture')
    p.data.update(recipient=deepcopy(snap['recipient']),shippingMethod=snap['shipping'])
    item=p.data['items'][0];item['assets']=[{'url':'https://fixture/art','printArea':'default','status':'complete'}]
    v=dict(id='00000000-0000-4000-8000-000000000001',environment='sandbox',allocation_id=snap['allocation_id'],snapshot=snap,
        source_snapshot=snap,order_id='99',item_id='88',url_hash=prep.digest('https://fixture/art'),status='Checking QA',
        browser={'verified':True,'full_image_fit_verified':True,'original_asset_id':'asset-id'})
    monkeypatch.setattr('prodigi_browser.checked',lambda *_:(snap,deepcopy(p.data),deepcopy(p.data['items'][0])))
    monkeypatch.setattr(full,'approve',lambda *_:approved(snap))
    doc=dict(url='https://sports-cave-image-factory.onrender.com/api/prodigi-document/'+'a'*43,output={'sha256':'fixture'})
    monkeypatch.setattr('prodigi_documents.create',lambda *_:doc)
    calls=[];saved=[]
    def slip(oid,url):
        calls.append((oid,url));p.data['packingSlip']={'url':url,'status':'ready'}
    p.packing_slip=slip
    return v,p,snap,calls,lambda x:saved.append(deepcopy(x))


def test_one_pass_checks_all_questions_and_preserves_manual_submission(pipeline):
    v,p,snap,calls,persist=pipeline
    result=full.run(v,p,lambda _:snap,persist)
    assert result['status']=='Ready for manual payment' and all(result['checks'].values())
    assert p.data['status']=='draft' and not p.data.get('charges') and len(calls)==1
    assert v['document_write_intent']
    full.run(v,p,lambda _:snap,persist)
    assert len(calls)==1


def test_uncertain_document_acknowledgement_never_uploads_again(pipeline):
    v,p,snap,calls,persist=pipeline
    def uncertain(*args):calls.append(args);raise ValueError('Uncertain acknowledgement')
    p.packing_slip=uncertain
    with pytest.raises(ValueError,match='Uncertain'):full.run(v,p,lambda _:snap,persist)
    assert v['document_write_intent'] and len(calls)==1
    with pytest.raises(ValueError,match='uncertain'):full.run(v,p,lambda _:snap,persist)
    assert len(calls)==1


def test_native_quality_failure_still_verifies_certificate_and_packing_slip(pipeline,monkeypatch):
    v,p,snap,calls,persist=pipeline
    monkeypatch.setattr(full,'approve',lambda *_:approved(snap,False))
    result=full.run(v,p,lambda _:snap,persist)
    assert result['status']=='Needs QA' and result['checks']['certificate'] and result['checks']['packing_slip']
    assert not result['checks']['production_approval'] and len(calls)==1


def test_qa_rejects_commercial_changes_during_document_attachment(pipeline):
    v,p,snap,calls,persist=pipeline
    def changed(oid,url):p.data['packingSlip']={'url':url,'status':'ready'};p.data['items'][0]['quantity']=2
    p.packing_slip=changed
    with pytest.raises(ValueError,match='order changed'):full.run(v,p,lambda _:snap,persist)


def test_multiple_numbered_items_require_document_review(pipeline):
    v,p,snap,calls,persist=pipeline;p.data['items'].append(deepcopy(p.data['items'][0]))
    with pytest.raises(ValueError,match='one numbered'):full.run(v,p,lambda _:snap,persist)
    assert not calls


def test_grid_success_links_only_to_exact_supplier_order():
    from orders_prodigi_grid import action_state,supplier_link
    assert action_state(None)['action']=='send'
    state=action_state({'status':'Ready for manual payment','order_id':'99'})
    assert state['tone']=='success' and state['url']=='https://dashboard.prodigi.com/orders/99/detail'
    assert supplier_link('99/other')=='' and supplier_link('https://other')==''
    assert action_state({'status':'Checking QA'})['action']==''
    assert action_state({'status':'Needs QA'})['tone']=='warning'
