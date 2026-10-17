"""Synthetic originals, storefronts, private receipts and disposable SQL only."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from PIL import Image
import auto_editions as ae
import auto_editions_visual as visual
from auto_editions_visual_store import Visual
from tests.test_auto_editions_quality import case,install
from tests.test_auto_editions_discovery import database,store,pglite_database,PID

@pytest.fixture
def visual_case(case,monkeypatch):
    c=case;m=c.record['manifest'];root=c.root
    # Trusted independent Photoshop-style composites, retaining real ICC bytes.
    for n in (1,3):
        with ae.compose(m,root,n) as image:image.save(root/f'reference-{n}.png',icc_profile=image.info['icc_profile'])
    shutil.copyfile(root/'reference-3.png',root/'original.png')
    c.record['proofs']=[ae.compare_reference(m,root,n,root/f'reference-{n}.png') for n in (1,3)]
    c.record['proofs'].append(ae.compare_original_outside_number(m,root,1,root/'original.png'))
    # Artwork is inset in a frame; it is cropped above the number for the
    # storefront corroboration. The exact full mockup hash is independently pinned.
    with Image.open(root/'original.png') as original,Image.new('RGB',(140,140),'black') as framed:
        framed.paste(original,(20,20));framed.save(root/'shopify.png')
    c.policy=dict(policy=visual.POLICY,id='synthetic-owner-visual',actor_id='synthetic-owner',approved_at='2026-01-01T00:00:00Z',
        owner_approved=True,download_scope='TEST_ONLY',reference_approval_evidence='Synthetic signed reference review',
        preparation_hash=c.record['hash'],source=m['source'],output=dict(dimensions=m['dimensions'],icc_sha256=c.standard['output']['icc_sha256']),
        references={n:dict(file_id='id:'+n,revision='ref1',sha256=ae.file_hash(root/n)) for n in ('original.png','reference-1.png','reference-3.png')},
        shopify=dict(product_gid=PID,media_id='gid://shopify/MediaImage/1',product_revision='2026-01-01T00:00:00Z',
            sha256=ae.file_hash(root/'shopify.png'),owner_reviewed_relationship=True,artwork_quad=[20,20,20,80,120,80,120,20],
            reference_region=[0,0,100,60],maximum_mean_error=0.01))
    def ref(spec,destination):shutil.copyfile(root/next(n for n,r in c.policy['references'].items() if r['file_id']==spec['file_id']),destination)
    def shopify(spec,destination):
        shutil.copyfile(root/'shopify.png',destination)
        return {k:c.policy['shopify'][k] for k in ('product_gid','media_id','product_revision')}
    c.providers=SimpleNamespace(metadata=lambda fid:c.source if fid==m['source']['file_id'] else c.read(fid),reference=ref,shopify=shopify,shopify_fence=lambda spec:True)
    c.assess=lambda:visual.assess(c.record,c.mapping,c.checkpoint,c.source,c.read,c.fetch,ref,shopify,[c.policy])
    monkeypatch.setenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED','true')
    monkeypatch.setattr(visual,'policies',lambda:[c.policy])
    return c

def test_exact_visual_approval_no_human_or_supplier_fabrication(visual_case):
    c=visual_case;check=c.assess();assert check['status']=='Auto Approved',check
    approval=visual.approval(check,c.record['manifest'])
    assert 'visual_approved' not in approval and approval['actor_id'].startswith('automatic:')
    assert ae.status(c.record['manifest'],approval)=='TEST READY'
    assert check['evidence']['print_ready'] is False and check['evidence']['fulfilment_authorized'] is False
    from auto_editions_quality import current_certificate
    assert not current_certificate(check,c.record['manifest'],[c.standard])
    assert c.record['hash']==ae.fingerprint(c.record['manifest'])

@pytest.mark.parametrize('change',['source','mapping','receipt','patch','proof','profile','reference','shopify_revision','shopify_false_match','missing_policy','revoked','unapproved','colour_only','number_position','plaque','fonts','geometry'])
def test_false_matches_and_changed_evidence_stay_pending(visual_case,change):
    c=visual_case;m=c.record['manifest']
    if change=='source':c.source['rev']='a2'
    if change=='mapping':c.mapping['dropbox_file_id']='id:different'
    if change=='receipt':c.metadata['id:master']['rev']='b2'
    if change=='patch':(c.root/'number-2.png').write_bytes(b'changed')
    if change=='proof':c.record['proofs'].pop()
    if change=='profile':c.policy['output']['icc_sha256']='f'*64
    if change=='reference':(c.root/'original.png').write_bytes(b'changed')
    if change=='shopify_revision':
        original=c.providers.shopify
        def changed(s,d):return {**original(s,d),'product_revision':'later'}
        c.assess=lambda:visual.assess(c.record,c.mapping,c.checkpoint,c.source,c.read,c.fetch,c.providers.reference,changed,[c.policy])
    if change=='shopify_false_match':
        # Same-looking thumbnail from a different product must fail identity.
        original=c.providers.shopify
        def changed(s,d):return {**original(s,d),'product_gid':'gid://shopify/Product/999'}
        c.assess=lambda:visual.assess(c.record,c.mapping,c.checkpoint,c.source,c.read,c.fetch,c.providers.reference,changed,[c.policy])
    if change=='missing_policy':c.policy['preparation_hash']='f'*64
    if change=='revoked':c.policy['revoked']=True
    if change=='unapproved':c.policy['owner_approved']=False
    if change=='colour_only':c.policy['reference_approval_evidence']=''
    if change=='number_position':m['number_region']=[0,0,20,10]
    if change=='plaque':m['plaque_bounds']=[0,0,1,1]
    if change=='fonts':m['source_inspection']['layers'][0]['fonts'][0]['installed']=False
    if change=='geometry':m['dimensions']=[200,200]
    assert c.assess()['status']!='Auto Approved'

def test_revocation_expiry_revision_and_kill_switch_fence_downloads(visual_case,monkeypatch):
    c=visual_case;m=c.record['manifest'];a=visual.approval(c.assess(),m)
    assert visual.current(a,m)
    c.policy['revoked']=True;assert ae.status(m,a)=='NOT CONFIGURED';c.policy.pop('revoked')
    assert not visual.current(a,m,now=datetime.now(timezone.utc)+timedelta(days=2))
    changed=deepcopy(m);changed['source']['revision']='a2';assert ae.status(changed,a)=='NOT CONFIGURED'
    monkeypatch.delenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED');assert ae.status(m,a)=='NOT CONFIGURED'

def test_store_reuses_existing_preparation_and_retains_allocation_history(visual_case,store):
    from auto_editions_status import batch
    from auto_editions_store import Preparations
    c=visual_case;d,sql=install(c,store)
    sql.execute('SELECT jsonb_agg(to_jsonb(a)) AS rows FROM edition_allocations a');allocations=sql.fetchone()['rows']
    snapshot={p.name:ae.file_hash(p) for p in c.root.iterdir() if p.is_file()}
    assets=SimpleNamespace(fetch=c.fetch)
    assert Visual(d.connect).run_one(assets,providers=c.providers)
    assert not Visual(d.connect).run_one(assets,providers=c.providers)
    sql.execute('SELECT status FROM auto_edition_onboarding');assert sql.fetchone()['status']=='Cloud Ready'
    sql.execute('SELECT approval FROM auto_edition_layouts');approval=sql.fetchone()['approval'];assert not approval.get('visual_approved')
    state=batch(d.connect,[PID])['rows'][0];assert state['status']=='Cloud Ready' and state['approval_status']=='Auto Approved',state
    index=Preparations(d.connect).layouts(PID);assert index[(PID,'*')]['approval']['method']==visual.POLICY
    from auto_editions_cloud import confirmed_job
    unit=dict(id=42,shopify_product_gid=PID,shopify_variant_id='456',edition_number=2,edition_total=3,
              allocation_valid=True,identity_enforced=True,status='assigned',allocation_index=1,
              shopify_order_id='synthetic-order',shopify_line_item_id='synthetic-line')
    preparation=Preparations(d.connect).for_unit(unit)
    job=confirmed_job(unit,{**c.mapping,'verified':True,'state':'Linked'},c.source,preparation)
    assert job['number']==2 and job['total']==3 and 'production' not in job
    sql.execute('SELECT jsonb_agg(to_jsonb(a)) AS rows FROM edition_allocations a');assert sql.fetchone()['rows']==allocations
    assert {p.name:ae.file_hash(p) for p in c.root.iterdir() if p.is_file()}==snapshot
    sql.execute('SELECT count(*) AS n FROM auto_edition_setup_audit WHERE event=%s',('automatic_visual_assessment',));assert sql.fetchone()['n']==1

def test_store_disabled_pause_failure_and_reference_policy_reuse(visual_case,store,monkeypatch):
    c=visual_case;d,sql=install(c,store);assets=SimpleNamespace(fetch=c.fetch)
    monkeypatch.delenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED');assert not Visual(d.connect).run_one(assets,providers=c.providers)
    monkeypatch.setenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED','true')
    from worker_health import set_pause
    set_pause(d.connect,True,'synthetic-owner');assert not Visual(d.connect).run_one(assets,providers=c.providers)
    set_pause(d.connect,False,'synthetic-owner');assert Visual(d.connect).run_one(assets,providers=c.providers)
    c.policy['revoked']=True
    assert Visual(d.connect).run_one(assets,providers=c.providers)
    sql.execute('SELECT status FROM auto_edition_onboarding');assert sql.fetchone()['status']=='Blocked'
    sql.execute('SELECT approval FROM auto_edition_layouts');assert not visual.current(sql.fetchone()['approval'],c.record['manifest'])

def test_store_final_source_change_never_approves(visual_case,store):
    c=visual_case;d,sql=install(c,store);original=c.providers.shopify_fence
    c.providers.shopify_fence=lambda spec:False
    assert Visual(d.connect).run_one(SimpleNamespace(fetch=c.fetch),providers=c.providers)
    sql.execute('SELECT count(*) AS n FROM auto_edition_layouts');assert sql.fetchone()['n']==0
    sql.execute('SELECT detail FROM auto_edition_setup_audit WHERE event=%s',('automatic_visual_assessment',));assert sql.fetchone()['detail']['assessment']['status']=='Needs Review'

def test_worker_health_labels_automatic_decisions_without_changing_completion_counts():
    from tests.test_worker_health import sample,NOW
    import worker_health as health
    args=sample('Cloud Ready');pid=args[0][0]['product_gid'];args[1][pid]['approval_status']='Auto Approved'
    report=health.project(*args,now=NOW)
    assert report['jobs'][0]['status']=='Auto Approved' and report['jobs'][0]['category']=='Completed'
    assert report['counts']['completed']==1

@pytest.mark.parametrize('change',['small_crop','degenerate_quad','crossed_quad','duplicate_policy','future_review','untrusted_mockup','production_scope'])
def test_untrusted_or_insufficient_registration_is_not_eligible(visual_case,change):
    c=visual_case;p=c.policy
    if change=='small_crop':p['shopify']['reference_region']=[0,0,5,5]
    if change=='degenerate_quad':p['shopify']['artwork_quad']=[0]*8
    if change=='crossed_quad':p['shopify']['artwork_quad']=[0,0,100,100,0,100,100,0]
    if change=='future_review':p['approved_at']='2099-01-01T00:00:00Z'
    if change=='untrusted_mockup':p['shopify']['owner_reviewed_relationship']=False
    if change=='production_scope':p['download_scope']='PRODUCTION'
    assert visual.policy_for(c.record,[p,p] if change=='duplicate_policy' else [p]) is None

def test_existing_human_approval_is_reused_without_automatic_replacement(visual_case,store):
    c=visual_case;d,sql=install(c,store)
    a=dict(actor_id='actual-owner',preparation_hash=c.record['hash'],pixel_exact=True,visual_approved=True,test_only=True)
    sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'*',%s,%s::jsonb)",(PID,c.record['hash'],json.dumps(a)))
    assert not Visual(d.connect).run_one(SimpleNamespace(fetch=lambda *a:pytest.fail('No refetch for existing human approval')),providers=c.providers)
    sql.execute('SELECT approval FROM auto_edition_layouts');assert sql.fetchone()['approval']==a
    sql.execute("UPDATE auto_edition_onboarding SET status='Cloud Ready'")
    # A previous uncertain machine assessment cannot revoke a later exact human
    # review or relabel it as an automated/human-fabricated decision.
    from auto_editions_status import batch
    sql.execute("INSERT INTO auto_edition_setup_audit(actor_id,preparation_hash,event,detail) VALUES(%s,%s,%s,%s::jsonb)",
                ('automatic:synthetic',c.record['hash'],'automatic_visual_assessment',json.dumps(dict(assessment=dict(status='Needs Review',reason='Old uncertain comparison')))))
    state=batch(d.connect,[PID])['rows'][0]
    assert state['status']=='Cloud Ready' and state['approval_status'] is None,state

def test_failed_provider_isolated_from_next_prepared_job(visual_case,store):
    c=visual_case;d,sql=install(c,store)
    def unavailable(*a):raise OSError('Synthetic outage')
    c.providers.metadata=unavailable
    assert Visual(d.connect).run_one(SimpleNamespace(fetch=c.fetch),providers=c.providers)
    assert not Visual(d.connect).run_one(SimpleNamespace(fetch=c.fetch),providers=c.providers)
    sql.execute("SELECT detail FROM auto_edition_setup_audit WHERE event=%s",('automatic_visual_assessment',))
    assert sql.fetchone()['detail']['assessment']['status']=='Failed'

def test_registered_perspective_corroboration_is_bounded(visual_case):
    # A reviewed quadrilateral may account for perspective. It remains only
    # corroboration: exact product/media/source/reference hashes are mandatory.
    c=visual_case;c.policy['shopify']['artwork_quad']=[20,20,25,80,115,80,120,20]
    assert c.assess()['status']=='Auto Approved'

def test_independent_reference_stops_altered_art_even_with_updated_transport_evidence(visual_case):
    c=visual_case;m=c.record['manifest']
    with Image.open(c.root/'master.png') as original:
        profile=original.info['icc_profile']
    with Image.new('RGB',(100,100),'blue') as image:image.save(c.root/'master.png',icc_profile=profile)
    m['master']['sha256']=ae.file_hash(c.root/'master.png');digest=ae.fingerprint(m)
    c.record['hash']=digest;c.record['receipts']['preparation_hash']=digest;c.policy['preparation_hash']=digest;c.checkpoint['preparation_hash']=digest
    for proof in c.record['proofs']:proof['preparation_hash']=digest
    from auto_editions_cloud import DropboxAssets
    for asset,receipt in zip([m['master'],*m['patches'].values()],c.record['receipts']['assets']):
        path=c.root/asset['name'];receipt['bytes']=path.stat().st_size
        c.metadata[receipt['file_id']].update(size=path.stat().st_size,content_hash=ae.file_hash(path,dropbox=True),path_display=DropboxAssets.path(digest,asset['name']))
    check=c.assess();assert check['status']=='Needs Review' and 'differs from the approved original' in check['reason'],check

@pytest.mark.parametrize('change',['mapping','edition_total','checkpoint','human','policy','feature'])
def test_concurrent_final_fences_preserve_newer_decisions(visual_case,store,monkeypatch,change):
    c=visual_case;d,sql=install(c,store)
    def fence(spec):
        if change=='mapping':sql.execute("UPDATE product_psd_mappings SET dropbox_file_id='id:changed'")
        if change=='edition_total':sql.execute('UPDATE edition_products SET edition_total=4')
        if change=='checkpoint':sql.execute("UPDATE auto_edition_onboarding SET status='Preparing'")
        if change=='human':
            a=dict(actor_id='actual-owner',preparation_hash=c.record['hash'],pixel_exact=True,visual_approved=True,test_only=True)
            sql.execute("INSERT INTO auto_edition_layouts(product_gid,variant_id,preparation_hash,approval) VALUES(%s,'*',%s,%s::jsonb)",(PID,c.record['hash'],json.dumps(a)))
        if change=='policy':monkeypatch.setattr(visual,'policies',lambda:[])
        if change=='feature':monkeypatch.delenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED')
        return True
    c.providers.shopify_fence=fence
    Visual(d.connect).run_one(SimpleNamespace(fetch=c.fetch),providers=c.providers)
    sql.execute('SELECT status FROM auto_edition_onboarding');assert sql.fetchone()['status']!='Cloud Ready'
    sql.execute('SELECT approval FROM auto_edition_layouts');row=sql.fetchone()
    assert row is None or row['approval']['actor_id']=='actual-owner'

def test_local_snapshot_audit_never_confuses_structural_proofs_with_approval(visual_case):
    from scripts.audit_auto_editions_visual import inspect
    c=visual_case
    row=dict(c.record,preparation_hash=c.record['hash'],source=c.record['manifest']['source'],product_gid=PID,
             file_id='id:original',dropbox_file_id='id:original',edition_total=3,current_total=3)
    check=inspect(row,[])
    assert check['decision']=='Needs Review' and check['checks']['original_proof']
    assert check['checks']['owner_reference_policy'] is False and check['regenerated'] is False and check['uploaded'] is False

@pytest.mark.parametrize('change',['conversion','icc_conflict','policy_revocation','policy_change'])
def test_visual_policy_never_overrides_uncertain_colour_intent(visual_case,monkeypatch,change):
    c=visual_case;m=c.record['manifest'];binding={'id':'synthetic-colour-policy','icc_sha256':c.policy['output']['icc_sha256']}
    m['colour_evidence']=dict(icc_sha256=c.policy['output']['icc_sha256'],pixels_converted=False,policy=binding)
    digest=ae.fingerprint(m);c.record['hash']=digest;c.policy['preparation_hash']=digest
    for p in c.record['proofs']:p['preparation_hash']=digest
    import auto_editions_colour_policy as colour
    monkeypatch.setattr(colour,'resolve',lambda source:(b'synthetic-profile',binding))
    assert visual.policy_for(c.record,[c.policy])
    if change=='conversion':m['colour_evidence']['pixels_converted']=True
    if change=='icc_conflict':m['colour_evidence']['icc_sha256']='f'*64
    if change=='policy_change':monkeypatch.setattr(colour,'resolve',lambda source:(b'changed',{'id':'different'}))
    if change=='policy_revocation':
        def revoked(source):raise ValueError('Colour policy awaiting approval')
        monkeypatch.setattr(colour,'resolve',revoked)
    digest=ae.fingerprint(m);c.policy['preparation_hash']=digest
    for p in c.record['proofs']:p['preparation_hash']=digest
    assert visual.policy_for(c.record,[c.policy]) is None

@pytest.mark.parametrize('mode',['approved','provider_failure','disabled'])
def test_new_import_reconciles_after_upload_without_second_transfer(visual_case,monkeypatch,mode):
    import asyncio
    from unittest.mock import Mock
    import auto_editions_setup_api as setup
    import auto_editions_onboarding_api as onboarding
    import auto_editions_visual_store as visual_store
    from tests.test_auto_editions_api import request
    c=visual_case;m=c.record['manifest'];digest=c.record['hash']
    grant=dict(actor_id='synthetic-owner',context=dict(automatic=True,product_gid=PID,lease_token='synthetic-lease',source=m['source'],number=1,total=3))
    assets=SimpleNamespace(publish_preparation=Mock(return_value=c.record['receipts']))
    registry=SimpleNamespace(save=Mock(return_value=digest))
    queue=SimpleNamespace(connect=lambda:None,imported_state=Mock(side_effect=['Blocked','Cloud Ready' if mode=='approved' else 'Blocked']),checkpoint=Mock())
    def reconcile(actual,**kw):
        assert actual is assets and kw['pid']==PID and Path(kw['local_root']).is_dir()
        if mode=='provider_failure':raise RuntimeError('Synthetic provider unavailable')
        return True
    runner=SimpleNamespace(run_one=Mock(side_effect=reconcile))
    monkeypatch.setattr(setup,'grant_context',lambda req:grant)
    monkeypatch.setattr(setup,'unpack',lambda *a:(m,c.record['proofs']))
    monkeypatch.setattr(setup.runtime,'storage',lambda:assets)
    monkeypatch.setattr(setup.runtime,'stores',lambda:(registry,None))
    monkeypatch.setattr(onboarding,'queue',lambda:queue)
    monkeypatch.setattr(visual_store,'Visual',lambda connect:runner)
    if mode=='disabled':monkeypatch.delenv('AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED')
    response=asyncio.run(setup.package(request('POST')));body=json.loads(response.body)
    assert response.status_code==200 and body['print_ready'] is False and grant['imported']==digest
    assert body['status']==('Cloud Ready' if mode=='approved' else 'Awaiting visual approval')
    assert assets.publish_preparation.call_count==registry.save.call_count==queue.checkpoint.call_count==1
    assert runner.run_one.call_count==(0 if mode=='disabled' else 1)
