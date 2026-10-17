"""Synthetic policies and isolated PSD metadata: never activate live defaults."""
from copy import deepcopy
from unittest.mock import Mock,patch,AsyncMock
import json,struct
import pytest
import auto_editions as ae
from auto_editions_colour_policy import propose,approve,resolve,fingerprint,validate
from auto_editions_colour_source import ColourReview,inspect_psd
from auto_editions_colour_workflows import verified_membership
from tests.test_auto_editions_colour import psd,icc,source,approved

E=dict(name='independent-workflow-report',sha256='1'*64,purpose='Synthetic designer/export lineage and trusted comparison')
SCOPE=dict(kind='verified_workflow',workflow_id='verified-canvas',mode='RGB',depth=8,
           identity='file_id+content_hash',default_for_untagged_rgb=True)


def policy():
    p=propose('reviewed-default',icc(),[dict(source=source(),provenance=E)],[E],[E],scope=SCOPE)
    return approve(p,'synthetic-owner',fingerprint(p))


def member(tmp_path,p=None):
    file=psd(tmp_path/'isolated.psd');s={**source(),'file_id':'id:new','content_hash':ae.file_hash(file,dropbox=True)}
    return file,s,verified_membership(p or policy(),file,s,[E],'synthetic-provenance-verifier')


def test_legacy_approval_identity_and_evidence_are_unchanged():
    p=approved(source());_,e=resolve(source(),[p])
    assert set(e)=={'group','approval_hash','owner','icc_sha256','pixels_converted'}
    for s in ({**source(),'revision':'new'},{**source(),'product_gid':'gid://shopify/Product/123'}):
        with pytest.raises(ColourReview):resolve(s,[p])


def test_workflow_extension_preserves_legacy_receipt_but_conflicts_still_block():
    old=approved(source());new=policy()
    assert resolve(source(),[old,new])[1]==resolve(source(),[old])[1]
    changed=bytearray(icc());changed[84:100]=b'2'*16
    p=propose('conflicting',bytes(changed),new['members'],[E],[E],scope=SCOPE)
    conflict=approve(p,'synthetic-owner',fingerprint(p))
    with pytest.raises(ColourReview):resolve(source(),[old,conflict])


def test_explicit_new_scope_reuses_reviewed_content_without_per_product_reapproval():
    p=policy();s={**source(),'revision':'a2','product_gid':'gid://shopify/Product/123'}
    assert resolve(s,[p])[1]['approval_hash']==p['approval_hash']
    with pytest.raises(ColourReview):resolve({**s,'content_hash':'b'*64},[p])
    with pytest.raises(ColourReview):resolve(s,[p,p])
    changed=deepcopy(p);changed['scope']['workflow_id']='different'
    with pytest.raises(ColourReview):resolve(s,[changed])


def test_configured_default_requires_verified_content_bound_workflow_receipt(tmp_path):
    p=policy();file,s,r=member(tmp_path,p)
    for args in ({},{'memberships':[r]},{'memberships':[],'default_group':p['group']}):
        with pytest.raises(ColourReview):resolve(s,[p],**args)
    _,e=resolve(s,[p],memberships=[r],default_group=p['group']);assert e['scope']==SCOPE
    assert resolve({**s,'revision':'a3'},[p],memberships=[r],default_group=p['group'])[1]==e
    with pytest.raises(ColourReview):resolve({**s,'content_hash':'b'*64},[p],memberships=[r],default_group=p['group'])
    with pytest.raises(ColourReview):resolve({**s,'file_id':'id:unknown'},[p],memberships=[r],default_group=p['group'])
    r['inspection']['mode']=4
    with pytest.raises(ColourReview):resolve(s,[p],memberships=[r],default_group=p['group'])


def test_membership_never_accepts_tagged_cmyk_changed_or_unknown_sources(tmp_path):
    p=policy();file,s,r=member(tmp_path,p)
    with pytest.raises(ColourReview):verified_membership(p,file,{**s,'content_hash':'f'*64},[E],'operator')
    with pytest.raises(ValueError):verified_membership(p,file,s,[],'operator')
    psd(file,icc());s['content_hash']=ae.file_hash(file,dropbox=True)
    with pytest.raises(ColourReview):verified_membership(p,file,s,[E],'operator')
    psd(file);b=bytearray(file.read_bytes());b[24:26]=struct.pack('>H',4);file.write_bytes(b);s['content_hash']=ae.file_hash(file,dropbox=True)
    with pytest.raises(ColourReview):verified_membership(p,file,s,[E],'operator')


def test_proposal_pins_source_and_never_applies_policy():
    from auto_editions_colour_review import proposal
    p=policy();view=dict(review_hash='snapshot',source=source(),can_propose=True)
    body=dict(review_hash='snapshot',reference_policy=p['approval_hash'],workflow_id='future-workflow',workflow_scope=True,provenance=E,references=[E],comparisons=[E])
    with patch('auto_editions_colour_review.snapshot',return_value=view),patch('auto_editions_colour_store.configuration',return_value=dict(policies=[p],memberships=[],default_group='')):
        result=proposal(Mock(),'pid',body)
        assert result['applied'] is False and result['proposal']['status']=='awaiting_approval'
        assert result['proposal']['scope']['workflow_id']=='future-workflow'
        with pytest.raises(ColourReview):validate(result['proposal'])
        with pytest.raises(ValueError,match='changed'):proposal(Mock(),'pid',{**body,'review_hash':'stale'})
        view['can_propose']=False
        with pytest.raises(ValueError,match='CMYK'):proposal(Mock(),'pid',body)


def test_review_endpoint_rejects_non_admin_and_forged_origin():
    import asyncio,auto_editions_status as status
    from tests.test_auto_editions_api import request,VA,ADMIN
    with patch.object(status,'actor',new=AsyncMock(return_value=VA)),patch.object(status,'can_write',return_value=False):
        assert asyncio.run(status.colour_review(request())).status_code==403
    import files_upload_api as files
    with patch.object(files,'_request_user',return_value=ADMIN),patch.object(status.runtime,'enabled',return_value=True),patch('os_accounts.can_access_page',return_value=True):
        assert asyncio.run(status.colour_review(request('POST',origin='https://evil.test'))).status_code==403


def test_snapshot_rejects_changed_mapping_or_retained_passed_design():
    from auto_editions_colour_review import snapshot
    cur=Mock();conn=Mock();connect=Mock(return_value=conn)
    conn.__enter__=Mock(return_value=conn);conn.__exit__=Mock(return_value=False)
    conn.cursor.return_value.__enter__=Mock(return_value=cur);conn.cursor.return_value.__exit__=Mock(return_value=False)
    cur.fetchone.return_value=dict(source=source(),dropbox_file_id='id:changed',preparation_hash=None)
    with pytest.raises(ValueError,match='Mapping changed'):snapshot(connect,source()['product_gid'])
    cur.fetchone.return_value=dict(source=source(),dropbox_file_id=source()['file_id'],preparation_hash='b'*64)
    with pytest.raises(ValueError,match='retained'):snapshot(connect,source()['product_gid'])


def test_colour_exception_action_is_explicit_and_passed_review_is_unchanged():
    import auto_editions_status as status
    from tests.test_auto_editions_status import record
    for why in ('Colour policy awaiting approval','ICC export mismatch','Print-colour incompatibility: RGB preparation required'):
        row={**record(), 'preparation_hash':None,'status':'Blocked','reason':why}
        value=status.project(row,writable=True)
        assert value['status']=='Needs Review' and value['actions']==['colour-review']
        assert status.project(row,writable=False)['actions']==[]
    assert status.project(record(),writable=True)['status']=='Cloud Ready'
