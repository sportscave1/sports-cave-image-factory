from copy import deepcopy
from unittest.mock import patch
import pytest
import print_specifications as specs
import print_jpg
from test_print_jpg import ready, family


def supplier(size='XL', factor=1):
    return {'frame':'Unframed','size':size,'prodigi_sku':'SYNTHETIC-'+size,'source':'synthetic supplier fixture only',
            'verification_status':'Verified supplier','pixel_dimensions':[600//factor,400//factor],
            'printable_mm':[300/factor,200/factor],'bleed_mm':[0,0,0,0],'margins_mm':[0,0,0,0],
            'colour':{'mode':'RGB','profile':'sRGB'}}


LAYOUT={'verified':True,'source':'synthetic layout approval','dimensions':[1200,800],'protected_bounds':[100,100,1100,700]}


def test_single_xl_master_shared_by_four_approved_sizes():
    entries=[supplier(size,factor) for size,factor in [('XL',1),('L',2),('M',4),('S',10)]]
    with patch.object(specs,'registry',return_value={'specifications':entries}):
        plans=[specs.master_plan('Unframed / '+size,LAYOUT) for size in ('XL','L','M','S')]
    assert all(p['status']=='Shared master' and p['shared_sizes']==['XL','L','M','S'] for p in plans)
    assert all(p['master']==entries[0] for p in plans)
    row,mapping,*_=ready()
    assert len({print_jpg.unit_identity(row,mapping,p['master']) for p in plans})==1


@pytest.mark.parametrize('change',[
    {'pixel_dimensions':[300,190]}, {'printable_mm':[150,90]},
    {'colour':{'mode':'RGB','profile':'Adobe RGB'}}, {'pixel_dimensions':[1200,800]},
    {'bleed_mm':[100,100,100,100]}, {'margins_mm':[100,100,100,100]},
])
def test_incompatible_target_never_shares(change):
    result=specs.compatible(supplier(),{**supplier('L',2),**change},LAYOUT)
    assert result['status']!='Shared master'


@pytest.mark.parametrize('layout',[None,{}, {**LAYOUT,'verified':False},
    {**LAYOUT,'dimensions':[1200,850]}, {**LAYOUT,'protected_bounds':[-1,0,100,100]},
    {**LAYOUT,'protected_bounds':[0,0,0,0]}, {**LAYOUT,'source':''}])
def test_unverified_or_incompatible_source_blocks(layout):
    assert specs.compatible(supplier(),supplier('L',2),layout)['status']!='Shared master'


def test_smaller_bleed_can_make_badge_unsafe_even_with_matching_ratio():
    result=specs.compatible(supplier(),{**supplier('S',10),'bleed_mm':[0,3,0,3]},LAYOUT)
    assert result['status']=='Separate layout' and 'bleed/safe' in result['reason']


def test_partial_family_only_reports_verified_compatible_sizes():
    entries=[supplier(),supplier('L',2),{**supplier('M',4),'verification_status':'Unverified'}]
    with patch.object(specs,'registry',return_value={'specifications':entries}):
        plan=specs.master_plan('Unframed / L',LAYOUT)
    assert plan['shared_sizes']==['XL','L'] and plan['sizes']['M']['status']=='Unverified'
    assert plan['sizes']['S']['status']=='Unverified'


def test_actual_registry_does_not_promote_provisional_outputs():
    assert specs.registry()['master_strategy']['master_size']=='XL'
    for frame in ('Black','Oak','White','Unframed'):
        plan=specs.master_plan(frame+' / L',LAYOUT)
        assert plan['status']=='Unverified' and not plan.get('shared_sizes')


def test_stale_layer_identity_blocked_and_large_artifact_not_reused():
    row,mapping,spec,processor,inspection=ready()
    with family(spec) as master:
        wrong=deepcopy(inspection);wrong['source_identity']['revision']='old'
        assert print_jpg.state(row,mapping,inspection=wrong,processor=processor)['label']=='Blocked'
        key=print_jpg.unit_identity(row,mapping,master)
        output={'identity':key,'validated':True,'quality_approved':True,'print_ready':True,
                'strategy':'largest_approved_size_first','dimensions':[12,8]}
        assert print_jpg.state(row,mapping,inspection=inspection,processor=processor,artifact=output)['label']=='Blocked'
        output['dimensions']=[24,16]
        assert print_jpg.state(row,mapping,inspection=inspection,processor=processor,artifact=output)['label']=='Download JPG'


def test_shared_master_download_requires_current_plan(tmp_path):
    from PIL import Image
    import hashlib
    file=tmp_path/'master.jpg';Image.new('RGB',(24,16)).save(file)
    record={'owner':'owner','identity':'key','validated':True,'quality_approved':True,'print_ready':True,
            'strategy':'largest_approved_size_first','dimensions':[24,16], 'jpg':str(file),
            'jpg_sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
    with pytest.raises(ValueError):print_jpg.verified_download(record,'key','owner',tmp_path)
    plan={'status':'Shared master','master':{'pixel_dimensions':[24,16]}}
    assert print_jpg.verified_download(record,'key','owner',tmp_path,plan=plan)==file
    with pytest.raises(ValueError):print_jpg.verified_download(record,'key','owner',tmp_path,plan={**plan,'status':'Separate layout'})


@pytest.mark.parametrize('change',[{'edition_number':-1},{'edition_number':2.5},{'edition_number':True},{'edition_total':'100'},{'allocation_index':-1}])
def test_invalid_unit_cannot_own_a_master(change):
    row,mapping,spec,*_=ready()
    with pytest.raises(ValueError):print_jpg.unit_identity({**row,**change},mapping,spec)


def test_local_proof_binds_exact_unit_and_replaced_text():
    from scripts.local_print_test import verified_unit
    unit={'source':'read_only_supabase','shopify_order_id':'order','shopify_line_item_id':'line','allocation_index':2,
          'allocation_id':8,'edition_number':2,'edition_total':100,'allocation_valid':True,'identity_enforced':True,
          'dropbox_file_id':'id:f','dropbox_revision':'r'}
    record={'product_gid':'p','order_unit':unit,'after_text':'002 / 100','dropbox_file_id':'id:f','dropbox_revision':'r'}
    evidence={'target':[{**unit,'shopify_product_gid':'p','shopify_variant_id':'variant'}]}
    assert verified_unit(record,evidence)['allocation_index']==2
    for change in [{'allocation_index':1},{'allocation_id':7},{'shopify_order_id':'other'},{'edition_number':3}]:
        with pytest.raises(ValueError):verified_unit({**record,'order_unit':{**unit,**change}},evidence)
    with pytest.raises(ValueError):verified_unit({**record,'after_text':'003 / 100'},evidence)
    with pytest.raises(ValueError):verified_unit(record,{'target':evidence['target']*2})
