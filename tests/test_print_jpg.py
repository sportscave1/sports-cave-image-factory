import hashlib
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
import pytest
from PIL import Image
import print_jpg
import print_specifications as specs


def ready():
    row={'shopify_order_id':'o','shopify_line_item_id':'l','allocation_index':1,'shopify_product_id':'p','variant_id':'v','edition_number':2,'edition_total':100,'variant':'Unframed / L','allocation_valid':True,'identity_enforced':True}
    mapping={'verified':True,'state':'Linked','dropbox_file_id':'id:f','revision':'rev','content_hash':'hash'}
    spec={'frame':'Unframed','size':'L','verification_status':'Verified supplier','prodigi_sku':'TEST','source':'test-only supplier fixture','pixel_dimensions':[12,8],'printable_mm':[12,8],'bleed_mm':[0,0,0,0],'margins_mm':[0,0,0,0],'colour':{'mode':'RGB','profile':'sRGB'}}
    processor={'authenticated':True,'capabilities':['verifiedPrintJpgV1']}
    inspection={'status':'Ready','verified_source':True,'source_identity':{'product':'p','file':'id:f','revision':'rev','hash':'hash'},'layout':{'verified':True,'source':'synthetic approved layout','dimensions':[12,8],'protected_bounds':[2,2,10,6]}}
    return row,mapping,spec,processor,inspection


@contextmanager
def family(spec):
    master={**spec,'size':'XL','prodigi_sku':'TEST_XL','pixel_dimensions':[24,16],'printable_mm':[24,16]}
    with patch.object(specs,'for_variant',return_value=spec), patch.object(specs,'registry',return_value={'specifications':[master,spec]}):
        yield master


def test_registry_preserves_sixteen_unverified_mappings():
    data=specs.registry();assert len(data['specifications'])==16
    assert data['storefront_references']['XL']['pixels_300ppi']==[10276,7323]
    assert not any(specs.verified(s) for s in data['specifications'])
    assert specs.for_variant('Unframed / L - 45 × 62 cm')['prodigi_sku']=='GLOBAL-FAP-A2'


def test_missing_or_invalid_unit_never_generates():
    row,mapping,*_=ready()
    assert print_jpg.state(row,None)['label']=='Needs Setup'
    row['allocation_valid']=False;assert print_jpg.state(row,mapping)['label']=='Blocked'


def test_verified_spec_does_not_imply_processor():
    row,mapping,spec,processor,inspection=ready()
    with family(spec):
        assert print_jpg.state(row,mapping,inspection=inspection)['label']=='Needs Setup'
        assert print_jpg.state(row,mapping,inspection=inspection,processor=processor)['label']=='Generate JPG'


def test_unit_product_revision_edition_and_variant_isolation():
    row,mapping,spec,*_=ready();initial=print_jpg.unit_identity(row,mapping,spec)
    for key,value in [('allocation_index',2),('edition_number',3),('shopify_product_id','other'),('shopify_line_item_id','other'),('variant_id','other')]:
        assert print_jpg.unit_identity({**row,key:value},mapping,spec)!=initial
    assert print_jpg.unit_identity(row,{**mapping,'revision':'new'},spec)!=initial


def test_duplicate_running_and_quality_review_states():
    row,mapping,spec,processor,inspection=ready()
    with family(spec) as master:
        key=print_jpg.unit_identity(row,mapping,master)
        kwargs={'inspection':inspection,'processor':processor}
        assert print_jpg.state(row,mapping,artifact={'identity':key,'status':'Generating'},**kwargs)['label']=='Generating'
        assert print_jpg.state(row,mapping,artifact={'identity':key,'validated':True,'quality_approved':False},**kwargs)['label']=='Review'
        assert print_jpg.state(row,mapping,artifact={'identity':'different'},**kwargs)['label']=='Blocked'


def test_local_download_requires_approval_owner_hash_size(tmp_path):
    file=tmp_path/'print.jpg';Image.new('RGB',(12,8)).save(file)
    record={'identity':'key','owner':'owner','validated':True,'quality_approved':True,'print_ready':True,'jpg':str(file),'jpg_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'dimensions':[12,8]}
    assert print_jpg.verified_download(record,'key','owner',tmp_path)==file
    for change in [{'quality_approved':False},{'owner':'other'},{'identity':'other'},{'dimensions':[1,1]},{'jpg_sha256':'bad'},{'print_ready':False}]:
        with pytest.raises(ValueError):print_jpg.verified_download({**record,**change},'key','owner',tmp_path)


def test_mobile_unit_identity_is_stable_before_and_after_normalisation():
    import orders_page as orders
    row={'shopify_order_id':'o','shopify_line_item_id':'l','allocation_index':2}
    assert orders._mobile_unit_id(row)==orders._mobile_unit_id(orders._normalise_row(row))
    assert orders._mobile_unit_id(row)!=orders._mobile_unit_id({**row,'allocation_index':1})
