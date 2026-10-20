"""Owner-selected presentation and fresh-export admission; all offline."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import pytest
from PIL import Image
import auto_editions as ae
import auto_editions_artwork_recovery as artwork
import auto_editions_role_evidence as roles
import auto_editions_onboarding as onboarding
import auto_editions_recovery as recovery
from tests.test_ordered_design_recovery import resolved_inspection


def test_owner_selected_number_ignores_only_exact_obsolete_field():
    selected=json.loads(roles.REGISTRY.read_text())['resolutions'][2]
    data=resolved_inspection(selected);data['document'].update(width_px=7016,height_px=4961);old=selected['hidden_number']
    data['layers'].append(dict(layer_id=old['layer_id'],path=[dict(name=old['name'])],kind='text',
                              visible=True,editable=True,bounds_px=old['bounds_px'],text=old['name']))
    before=deepcopy(data)
    assert onboarding.detect_roles(data,100,source=selected['source'])['number_layer']=='No. 027 / 100'
    assert data==before
    data['layers'][-1]['layer_id']+=1
    with pytest.raises(ValueError,match='Pinned'):onboarding.detect_roles(data,100,source=selected['source'])
    with pytest.raises(ValueError):onboarding.detect_roles(before,100,source={**selected['source'],'revision':'changed'})


def test_reviewed_black_backing_preserves_icc_and_unbacked_original(tmp_path):
    selected=json.loads(roles.REGISTRY.read_text())['resolutions'][0]
    icc=b'exact-valid-profile-bytes-preserved';path=tmp_path/'master.png'
    Image.new('RGBA',(20,10),(200,100,50,128)).save(path,icc_profile=icc)
    before=path.read_bytes()
    proof=artwork.verify_exports(tmp_path,{},selected['source'],['master.png'])
    assert (tmp_path.parent/'artwork-recovery-backups'/tmp_path.name/'unbacked-exports/master.png').read_bytes()==before
    with Image.open(path) as im:
        assert im.mode=='RGB' and im.info['icc_profile']==icc and im.getpixel((0,0))==(100,50,25)
    assert proof['unbacked_exports_preserved'] is True
    artwork.require_export_evidence(dict(source=selected['source'],artwork_recovery=proof))
    with pytest.raises(ValueError,match='presentation evidence'):artwork.require_export_evidence(dict(source=selected['source']))


def test_unknown_source_transparency_is_never_changed(tmp_path):
    path=tmp_path/'master.png';Image.new('RGBA',(20,10),(200,100,50,128)).save(path)
    before=path.read_bytes();selected=json.loads(roles.REGISTRY.read_text())['resolutions'][0]
    assert artwork.verify_exports(tmp_path,{}, {**selected['source'],'revision':'unknown'},['master.png']) is None
    assert path.read_bytes()==before and not (tmp_path/'unbacked-exports').exists()


@pytest.mark.parametrize('outside_change',[False,True])
def test_hidden_number_changes_cannot_escape_plaque(tmp_path,outside_change):
    selected=dict(hidden_number=dict(name='obsolete',layer_id=4),plaque=dict(bounds_px=[2,2,8,8]))
    before=Image.new('RGB',(10,10),'white');before.save(tmp_path/'uncorrected.png')
    after=before.copy();after.putpixel((1,1) if outside_change else (4,4),(0,0,0));after.save(tmp_path/'original.png')
    with patch.object(artwork,'resolution',return_value=selected):
        if outside_change:
            with pytest.raises(ValueError,match='outside the approved plaque'):artwork.verify_exports(tmp_path,dict(preparation_geometry=dict(scale=1)),{},[])
        else:assert artwork.verify_exports(tmp_path,dict(preparation_geometry=dict(scale=1)),{},[])['outside_plaque_exact'] is True


def test_backing_is_one_bounded_retry_for_exact_source_only():
    selected=json.loads(roles.REGISTRY.read_text())['resolutions'][0]
    row=dict(status='Blocked',priority=8,source=selected['source'],dropbox_file_id=selected['source']['file_id'],reason='Preparation failed: Master must be a lossless RGB PNG at the prepared size.. Existing PSD and mapping are preserved.')
    d=recovery.classify(row,{})
    assert d['action']=='retry_roles' and d['max_attempts']==1
    row['source']={**row['source'],'content_hash':'a'*64}
    assert recovery.classify(row,{})['action'] is None


def test_repair_admission_never_certifies_missing_cloud_receipts(tmp_path):
    from tests.test_auto_editions_bulk import prepared
    from auto_editions_technical import repair_evidence,certificate
    record,_=prepared(tmp_path);m=record['manifest']
    m.update(number_layer_name='number',plaque_layer_name='SC_EDITION_PLAQUE',source_inspection=dict(
        document=dict(width_px=200,height_px=100,profile='sRGB',mode='RGB',bits_per_channel=8),layers=[
        dict(path=[dict(name='number')],kind='text',text='001 / 2',editable=True,visible=True,fonts=[dict(installed=True)],bounds_px=[70,60,90,70]),
        dict(path=[dict(name='SC_EDITION_PLAQUE')],visible=True,bounds_px=[60,50,100,80])]))
    record['hash']=ae.fingerprint(m)
    for p in record['proofs']:p['preparation_hash']=record['hash']
    record['receipts']={}
    assert repair_evidence(record)==dict(repair_only=True,source=m['source'],colour_policy=None)
    with pytest.raises(ValueError,match='immutable'):certificate(record)
    record['proofs']=[]
    with pytest.raises(ValueError,match='proofs'):repair_evidence(record)
