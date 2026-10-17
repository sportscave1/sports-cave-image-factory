"""Synthetic review plans and local export reuse; no providers or live records."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import shutil
import pytest
from PIL import Image
import auto_editions as ae
from auto_editions_colour_audit import review_catalogue
from auto_editions_colour_review_exports import stage_export_review
from auto_editions_colour_policy import resolve
from auto_editions_colour_source import ColourReview,profile_info
from tests.test_auto_editions_colour import source,icc,psd,approved
from tests.test_auto_editions import package

NOW=datetime(2026,10,16,tzinfo=timezone.utc)


def inspection():
    return dict(document=dict(width_px=200,height_px=100,profile=None),layers=[
        dict(path=[dict(name='Number')],kind='text',text='01 / 02',visible=True,editable=True,
             fonts=[dict(installed=True)],layout=dict(font='ExactFont'),bounds_px=[70,60,90,70]),
        dict(path=[dict(name='SC_EDITION_PLAQUE')],kind='raster',visible=True,bounds_px=[60,50,100,80])])


def row(**changes):
    s=source()
    return dict(product_gid=s['product_gid'],product_title='Synthetic Artwork',mapped_file_id=s['file_id'],
        checkpoint_file_id=s['file_id'],inventory_revision=s['revision'],inventory_content_hash=s['content_hash'],
        product_edition_total=2,status='Needs PSD Repair',reason='Original PSD colour profile is unavailable',
        source=s,priority=1,preparation_hash=None,stored_preparations=0,lease_until=None,replacement=None,**changes)


def evidence():
    return dict(product_gid=source()['product_gid'],source=source(),fresh_revision_matches=True,source_hash_verified=True,
        binary_document=dict(state='untagged',mode=3,depth=8,width=200,height=100),retained_inspection=inspection())


def test_untagged_review_is_pending_and_template_approval_does_not_extend():
    result=review_catalogue([row()],[evidence()],now=NOW)
    assert result['counts']=={'propose_srgb_legacy_policy':1}
    assert result['automatic_retry_authorized'] is False and result['legacy_colour_approval_granted'] is False
    assert result['rows'][0]['colour_approved'] is False
    template=approved(source());template['members'][0]['source']={'template_id':'base','file_id':'id:base','revision':'a1','content_hash':'1'*64}
    with pytest.raises(ColourReview):resolve(source(),[template])


def test_all_45_prepared_rows_are_excluded_even_with_failure_reasons():
    rows=[]
    for n in range(45):
        r=row();r.update(product_gid=f'gid://shopify/Product/{1000+n}',preparation_hash=str(n)*64);rows.append(r)
    result=review_catalogue(rows,[],now=NOW)
    assert result['protected_prepared']==45 and result['counts']=={'retain_prepared':45}


@pytest.mark.parametrize('fault',['source','mapping','metadata','hash','structure','runtime','active','replacement'])
def test_uncertain_evidence_stays_pending(fault):
    r,e=row(),evidence()
    if fault=='source':e['source']={**source(),'revision':'a2'}
    if fault=='mapping':r['checkpoint_file_id']='id:other'
    if fault=='metadata':e['fresh_revision_matches']=False
    if fault=='hash':e['source_hash_verified']=False
    if fault=='structure':e['retained_inspection']['layers']=[]
    if fault=='runtime':r['reason']='Preparation failed: RuntimeError'
    if fault=='active':r['status']='Preparing'
    if fault=='replacement':r['replacement']={'stage':'Queued'}
    decision=review_catalogue([r],[e],now=NOW)['rows'][0]
    assert decision['decision'].startswith('pending_') and decision['colour_approved'] is False


def test_review_plan_keeps_paid_first_and_records_lease_hold():
    first=row();second=deepcopy(first);second.update(product_gid='gid://shopify/Product/999',priority=8,
        lease_until=(NOW+timedelta(minutes=30)).isoformat())
    e=evidence();e2=deepcopy(e);e2.update(product_gid=second['product_gid'],source={**source(),'product_gid':second['product_gid']})
    second['source']=e2['source']
    result=review_catalogue([first,second],[e,e2],now=NOW)
    assert result['rows'][0]['priority']==8 and result['rows'][0]['lease_hold_until']
    assert result['paid_unprepared']==1


def test_only_proven_pinned_tagged_omission_gets_an_export_recovery_plan():
    r=row();r['reason']='ICC export mismatch'
    e=evidence();e.update(binary_document={'state':'tagged','mode':3,'depth':8,'profile':profile_info(icc())},omission_proven=True)
    assert review_catalogue([r],[e],now=NOW)['rows'][0]['decision']=='plan_embedded_profile_export_recovery'
    e['omission_proven']=False
    assert review_catalogue([r],[e],now=NOW)['rows'][0]['decision']=='pending_uncertain'


def test_old_omission_evidence_never_overrides_an_unrelated_current_failure():
    r=row();r['reason']='Upload interrupted'
    e=evidence();e.update(binary_document={'state':'tagged','mode':3,'depth':8,'profile':profile_info(icc())},omission_proven=True)
    assert review_catalogue([r],[e],now=NOW)['rows'][0]['decision']=='pending_uncertain'


def test_duplicate_mapping_identities_are_not_silently_deduplicated():
    with pytest.raises(ValueError,match='Ambiguous'):review_catalogue([row(),row()],[],now=NOW)


def retained(tmp_path):
    folder=tmp_path/'retained';folder.mkdir();m=package(folder)
    for n in (1,2):
        with ae.compose(m,folder,n) as image:image.save(folder/f'reference-{n}.png')
    shutil.copyfile(folder/'reference-1.png',folder/'original.png')
    d=inspection();d['document']['profile']=profile_info(icc())['description']
    report={**m,'source_inspection':d,'number_layer_name':'Number','plaque_layer_name':'SC_EDITION_PLAQUE',
        'export_profiles':{p.name:profile_info(icc())['description'] for p in folder.glob('*.png')}}
    (folder/'preparation.json').write_text(json.dumps(report),encoding='utf-8')
    original=psd(tmp_path/'source.psd',icc(),width=200,height=100)
    return original,folder,{**source(),'content_hash':ae.file_hash(original,dropbox=True)}


def test_retained_exports_are_copied_and_proved_without_modifying_originals(tmp_path):
    original,folder,identity=retained(tmp_path)
    before={p.name:p.read_bytes() for p in folder.iterdir()};source_before=original.read_bytes()
    result=stage_export_review(original,folder,tmp_path/'review',identity,2)
    assert result['restored_exports']==6 and result['uploaded'] is False and result['retry_authorized'] is False
    assert result['original_source_unchanged'] and result['original_exports_unchanged']
    assert all(p.get('pixel_exact',p.get('outside_number_exact')) for p in result['proofs'])
    assert before=={p.name:p.read_bytes() for p in folder.iterdir()} and original.read_bytes()==source_before
    from auto_editions_package import unpack
    output=tmp_path/'unpacked';output.mkdir()
    manifest,proofs=unpack(tmp_path/'review/review-package.zip',output,identity,1,2)
    assert manifest['source']==identity and manifest['print_ready'] is False and proofs


def test_conflicting_icc_is_never_replaced_in_a_review_copy(tmp_path):
    original,folder,identity=retained(tmp_path)
    different=bytearray(icc());different[84:100]=b'5'*16
    with Image.open(folder/'master.png') as image:image.save(folder/'conflict.png',icc_profile=bytes(different))
    (folder/'conflict.png').replace(folder/'master.png')
    before=(folder/'master.png').read_bytes()
    with pytest.raises(ValueError,match='Conflicting'):stage_export_review(original,folder,tmp_path/'review',identity,2)
    assert (folder/'master.png').read_bytes()==before and not (tmp_path/'review/manifest.json').exists()


def test_source_hash_and_authoritative_edition_total_are_required(tmp_path):
    original,folder,identity=retained(tmp_path)
    with pytest.raises(ValueError,match='content changed'):
        stage_export_review(original,folder,tmp_path/'review',{**identity,'content_hash':'0'*64},2)
    with pytest.raises(ValueError,match='edition limit'):
        stage_export_review(original,folder,tmp_path/'review',identity,3)
