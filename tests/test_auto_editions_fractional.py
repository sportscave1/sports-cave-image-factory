"""Offline sizing/cache tests; not evidence of native Photoshop appearance or RSS."""
from copy import deepcopy
import json
import sys
from pathlib import Path
from unittest.mock import patch
import zipfile

import pytest
import auto_editions as ae
import auto_editions_resolution as resolution
import auto_editions_preparation_geometry as geometry
from test_auto_editions import package
from test_auto_editions_speed import async_test


def planned(source, variant='Black / XL'):
    return geometry.for_context(source, dict(variant_title=variant))


def description(record):
    scale=record['scale']
    return dict(scale=scale, method='native' if scale==1 else 'photoshop_layered_bicubic_smoother',
                supplier_verified=False, aspect_preserved=True, quality_approval_required=scale!=1, plan=record)


def test_sc3340_fractional_target_without_stretch_or_crop():
    record=planned([7016,4961])
    assert record['required_dimensions']==[11340,8016]
    assert record['output_dimensions']==[11340,8018]
    assert record['scale']==pytest.approx(1.616305587229)
    assert 11340*8018 < ae.WORKER_MAX_PIXELS
    assert record['estimate_before_supplier_crop'] and not record['bleed_verified']
    assert record['print_ready'] is False and record['supplier_verified'] is False
    assert record['resolution_status']=='target_met'
    geometry.validate([7016,4961],record['output_dimensions'],description(record))


def test_existing_jake_success_is_preserved_and_new_native_preparation_meets_reference():
    jake=planned([2835,2004])
    assert jake['output_dimensions']==[11340,8016] and jake['scale']==4
    native=planned([9933,7016])
    assert native['output_dimensions']==[11349,8016] and native['scale']>1


def test_smaller_selected_size_never_shrinks_shared_xl_master():
    assert planned([7016,4961],'Black / S')==planned([7016,4961],'Black / XL')
    assert geometry.for_context([7016,4961],dict(preparation_variants=['Black / M','Oak / L']))['required_dimensions']==[11340,8016]
    assert geometry.for_context([7016,4961],dict(supplier_sku='GLOBAL-CFP-A1'))['output_dimensions']==[11340,8018]


def test_unknown_unframed_and_missing_variant_never_inherit_a1():
    for title in ['', None, 'Unframed / XL', 'unmapped']:
        record=planned([7016,4961],title)
        assert record['references']==[] and record['resolution_status']=='target_not_verified'
        assert record['output_dimensions']==[7016,4961]


def test_known_crop_and_bleed_affect_target_without_cropping_artwork(monkeypatch):
    # Supplier canvas includes its declared bleed. Do not add bleed twice.
    spec=dict(sku='SYNTHETIC',printable_mm=[254,127],pixel_dimensions=[3000,1500],
              recommended_ppi=300,includes_bleed=True,source='offline fixture')
    monkeypatch.setattr(geometry,'references',lambda *args:[spec])
    uncropped=geometry.plan([2000,1000],1)
    assert uncropped['output_dimensions']==[3000,1500]
    cropped=geometry.plan([2000,1000],1,crop_bounds_px=[500,250,1500,750])
    assert cropped['output_dimensions']==[6000,3000]
    assert cropped['bleed_verified'] is True and cropped['estimate_before_supplier_crop'] is False
    assert cropped['source_dimensions']==[2000,1000]  # No trim or silent crop.


def test_over_budget_keeps_bounded_legacy_result_and_discloses_shortfall(monkeypatch):
    spec=dict(sku='SYNTHETIC',printable_mm=[2000,1000],pixel_dimensions=[23622,11811],
              recommended_ppi=300,includes_bleed=True,source='offline fixture')
    monkeypatch.setattr(geometry,'references',lambda *args:[spec])
    record=geometry.plan([7016,4961],1)
    assert record['output_dimensions']==[7016,4961]
    assert record['requested_dimensions'][0]*record['requested_dimensions'][1]>95_000_000
    assert record['resolution_status']=='below_target_worker_budget'
    assert record['worker_max_pixels']==ae.WORKER_MAX_PIXELS==95_000_000


def test_fractional_manifest_validates_but_old_archived_manifest_remains_valid(tmp_path):
    old=package(tmp_path)
    ae.validate_manifest(old)
    record=planned([7016,4961])
    new={**old, 'source_dimensions':[7016,4961], 'dimensions':record['output_dimensions'],
         'upscaled':True, 'preparation_geometry':description(record)}
    ae.validate_manifest(new)
    assert ae.fingerprint(old)!=ae.fingerprint(new)
    ae.validate_manifest(old)  # No version requirement applied to historical archives.
    corrupt=deepcopy(new);corrupt['dimensions'][1]+=1
    with pytest.raises(ValueError,match='pinned proportional'):ae.validate_manifest(corrupt)


def test_fractional_prepared_assets_use_unchanged_encoder_and_relative_patch_position(tmp_path,monkeypatch):
    from PIL import Image,ImageCms,JpegImagePlugin
    manifest=package(tmp_path)
    spec=dict(sku='SYNTHETIC',printable_mm=[25.4,12.7],pixel_dimensions=[300,150],
              recommended_ppi=300,includes_bleed=True,source='offline fixture')
    monkeypatch.setattr(geometry,'references',lambda *args:[spec])
    record=geometry.plan([200,100],1)
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    Image.new('RGB',(300,150),'navy').save(tmp_path/'master.png',icc_profile=profile)
    for n,colour in [(1,'white'),(2,'red')]:
        Image.new('RGB',(30,15),colour).save(tmp_path/f'number-{n}.png',icc_profile=profile)
        manifest['patches'][str(n)]['sha256']=ae.file_hash(tmp_path/f'number-{n}.png')
    manifest.update(dimensions=[300,150],source_dimensions=[200,100],upscaled=True,
                    preparation_geometry=description(record),number_region=[105,90,135,105])
    manifest['master']['sha256']=ae.file_hash(tmp_path/'master.png')
    with ae.compose(manifest,tmp_path,2) as image:
        assert image.getpixel((105,90))==(255,0,0)
        assert image.getpixel((104,90))==(0,0,128)
        assert manifest['number_region'][0]/300==70/200
        assert manifest['number_region'][1]/150==60/100
    output=ae.render_jpg(manifest,tmp_path,2,tmp_path/'fractional-002-TEST.jpg')
    with Image.open(tmp_path/'fractional-002-TEST.jpg') as image:
        assert image.size==(300,150) and image.info['icc_profile']==profile
        assert image.info['dpi']==(300,300) and JpegImagePlugin.get_sampling(image)==0
        assert all(v==1 for table in image.quantization.values() for v in table)
    assert output['print_ready'] is False and output['edition_number']==2


def test_resolution_information_preserves_fractional_source_evidence():
    record=planned([7016,4961])
    job=dict(manifest=dict(source_dimensions=[7016,4961],dimensions=record['output_dimensions'],
                          preparation_geometry=description(record)),archive_labels=dict(variant_title='Black / XL'))
    info=resolution.for_job(job,dict(dimensions=record['output_dimensions'],test_only=True,ppi_metadata=[300,300]))
    assert info['status']=='meets_recommendation' and info['source_provenance']=='recorded'
    assert min(info['native_canvas_ppi'])<213 and min(info['exported_ppi'])>299.99
    assert 'enlargement' in info['summary'] and info['output_status']=='TEST / NOT PRINT READY'
    assert info['estimate'] is True


def test_package_reuse_requires_target_version_dimensions_and_current_spec(tmp_path,monkeypatch):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/studio'))
    import auto_editions_local as local
    root=tmp_path/'host';folder=root/'job';folder.mkdir(parents=True)
    ctx=dict(automatic=True,source=dict(file_id='id:pinned',revision='rev'),total=100,variant_title='Black / XL')
    old=dict(source=ctx['source'],edition_total=100,source_dimensions=[7016,4961],dimensions=[7016,4961],
             preparation_geometry=dict(scale=1),colour_evidence=dict(icc_sha256='a'*64,pixels_converted=False))
    archive=folder/'prepared.zip'
    def save(manifest):
        with zipfile.ZipFile(archive,'w') as z:z.writestr('manifest.json',json.dumps(manifest))
    monkeypatch.setattr(local,'HOST_FILE',root/'host.dpapi')
    save(old);assert local.find_reusable_package(ctx) is None
    record=planned([7016,4961]);new={**old,'dimensions':record['output_dimensions'],'preparation_geometry':description(record)}
    save(new);assert local.find_reusable_package(ctx)==archive
    new['preparation_geometry']['plan']['version']='old-policy'
    save(new);assert local.find_reusable_package(ctx) is None
    record=planned([7016,4961]);new['preparation_geometry']=description(record);save(new)
    spec=deepcopy(resolution._editor_evidence());spec['GLOBAL-CFP-A1']['recommended_ppi']=400
    with patch.object(resolution,'_editor_evidence',return_value=spec):
        assert local.find_reusable_package(ctx) is None
    assert archive.exists()  # Mismatch never deletes/invalidates any archive.


def test_explicit_manual_scale_is_bound_without_changing_automatic_jake_policy():
    ctx=dict(variant_title='Black / XL')
    record=geometry.for_context([2835,2004],ctx,legacy_scale=1)
    manifest=dict(source_dimensions=[2835,2004],dimensions=record['output_dimensions'],
                  preparation_geometry=description(record))
    assert geometry.matches(manifest,ctx)
    assert not geometry.matches(manifest,{**ctx,'automatic':True})
    assert planned([2835,2004])['output_dimensions']==[11340,8016]


@async_test
async def test_fresh_package_intake_rejects_undersized_cache_before_any_publish():
    from unittest.mock import Mock
    import auto_editions_setup_api as setup
    from test_auto_editions_api import request
    ctx=dict(variant_title='Black / XL',source={},number=59,total=100)
    old=dict(source_dimensions=[7016,4961],dimensions=[7016,4961],preparation_geometry=dict(scale=1))
    with patch.object(setup,'grant_context',return_value=dict(context=ctx)), \
         patch.object(setup,'unpack',return_value=(old,[])),patch.object(setup.runtime,'storage') as storage:
        response=await setup.package(request('POST'))
        assert response.status_code==409
        assert b'Preparation target or policy changed' in response.body
        storage.assert_not_called()


def test_budget_shortfall_is_visible_without_readiness_promotion(monkeypatch):
    record=planned([7016,4961]);record['resolution_status']='below_target_worker_budget'
    job=dict(manifest=dict(source_dimensions=[7016,4961],dimensions=record['output_dimensions'],
                          preparation_geometry=description(record)),archive_labels=dict(variant_title='Black / XL'))
    info=resolution.for_job(job,dict(dimensions=record['output_dimensions'],test_only=True))
    assert any('95 MP' in note and 'no target success' in note for note in info['notes'])
    assert info['output_status']=='TEST / NOT PRINT READY'


@pytest.mark.parametrize('source',[[4961,7016],[7000,5001],[4200,3151]])
def test_proportional_rounding_stays_within_one_pixel_and_target(source):
    record=planned(source)
    output=record['output_dimensions']
    if record['resolution_status']=='target_met':
        assert all(a>=b for a,b in zip(output,record['required_dimensions']))
    assert abs(output[1]-source[1]*output[0]/source[0])<=.5


def test_extendscript_scale_serialization_retains_exact_pixel_and_cache_checks():
    record=planned([7016,4961]);record['scale']=1.61630558722919
    meta=description(record)
    geometry.validate([7016,4961],[11340,8018],meta)
    manifest=dict(source_dimensions=[7016,4961],dimensions=[11340,8018],preparation_geometry=meta)
    assert geometry.matches(manifest,dict(automatic=True,variant_title='Black / XL'))
    meta['scale']=1.41576
    with pytest.raises(ValueError):geometry.validate([7016,4961],[11340,8018],meta)
    meta['scale']=record['scale'];manifest['dimensions']=[11340,8017]
    assert not geometry.matches(manifest,dict(automatic=True,variant_title='Black / XL'))


from tests.test_auto_editions_jobs import database

@pytest.mark.parametrize('with_orders',[False,True])
def test_shared_variant_context_query_runs_on_postgres_without_cross_product_data(database,with_orders):
    from unittest.mock import Mock
    import auto_editions_onboarding_api as onboarding
    jobs,sql=database
    sql.execute("CREATE TABLE auto_edition_onboarding(product_gid text,status text,lease_token text,lease_until timestamptz,file_id text,source jsonb)")
    sql.execute("CREATE TABLE product_psd_mappings(shopify_product_gid text,dropbox_file_id text)")
    sql.execute("CREATE TABLE edition_products(shopify_product_gid text,shopify_product_id text,edition_total int,product_title text)")
    sql.execute("CREATE TABLE shopify_order_lines(shopify_product_id text,raw_json jsonb)")
    sql.execute("CREATE TABLE shopify_products(shopify_product_id text,raw_json jsonb)")
    pid='gid://shopify/Product/123'
    sql.execute("INSERT INTO auto_edition_onboarding VALUES(%s,'Preparing','lease',now()+interval '1 hour','id:source123',NULL)",(pid,))
    sql.execute("INSERT INTO product_psd_mappings VALUES(%s,'id:source123')",(pid,))
    sql.execute("INSERT INTO edition_products VALUES(%s,'123',100,'Synthetic artwork')",(pid,))
    for product,variants in [(pid,['Black / XL','White / Small','Black / XL']),('999',['Other / XXL'])]:
        sql.execute("INSERT INTO shopify_products VALUES(%s,%s::jsonb)",(product,json.dumps(dict(variants=[dict(title=v) for v in variants]))))
    if with_orders:
        for product,variant in [('123','Black / XL'),(pid,'White / Small'),('123','Black / XL'),('999','Other / XXL')]:
            sql.execute("INSERT INTO shopify_order_lines VALUES(%s,%s::jsonb)",(product,json.dumps(dict(variant_title=variant))))
    assets=Mock();assets.integration.psd_open_metadata.return_value=dict(id='id:source123',rev='abcdef1234567890',content_hash='a'*64,size=1,name='original.psd')
    with patch.object(onboarding,'queue',return_value=Mock(connect=jobs.connect)),patch.object(onboarding.runtime,'storage',return_value=assets),patch('auto_editions_v17.enabled',return_value=False):
        ctx=onboarding.product_context(pid,'lease')
    assert ctx['preparation_variants']==['Black / XL','White / Small']
    assert geometry.for_context([7016,4961],ctx)['output_dimensions']==[11340,8018]


@pytest.mark.parametrize('source,expected',[([2362,1670],[11340,8018]),([1670,2362],[8018,11340])])
def test_for_brock_reference_floor_is_proportional_and_within_existing_budget(source,expected):
    record=planned(source)
    assert record['output_dimensions']==expected
    assert expected[0]*expected[1]<=95_000_000
    assert record['source_dimensions']==source and record['resolution_status']=='target_met'
    target=record['quality_target']
    assert target['references'][0]['product_gid']=='gid://shopify/Product/15411172376883'
    assert target['supplier_rating_verified'] is False and record['print_ready'] is False
    geometry.validate(source,expected,description(record))


def test_legacy_plan_remains_valid_but_cannot_be_reused_as_new_reference_sizing():
    with patch.object(geometry,'quality_references',return_value={}),patch.object(geometry,'VERSION',geometry.LEGACY_VERSION):
        record=planned([7016,4961])
    record.pop('quality_target')
    assert record['output_dimensions']==[9933,7024]
    meta=description(record);geometry.validate([7016,4961],[9933,7024],meta)
    manifest=dict(source_dimensions=[7016,4961],dimensions=[9933,7024],preparation_geometry=meta)
    before=deepcopy(manifest)
    assert not geometry.matches(manifest,dict(automatic=True,variant_title='Black / XL'))
    assert manifest==before


def test_reference_sizing_is_disclosed_without_claiming_supplier_excellent():
    record=planned([2362,1670])
    job=dict(manifest=dict(source_dimensions=[2362,1670],dimensions=record['output_dimensions'],
                          preparation_geometry=description(record)),archive_labels=dict(variant_title='Black / XL'))
    info=resolution.for_job(job,dict(dimensions=record['output_dimensions'],test_only=True))
    assert any('The Final Lap #17' in n and '11340' in n for n in info['notes'])
    assert info['output_status']=='TEST / NOT PRINT READY'


def test_quality_policy_and_geometry_are_bound_into_package_generation(tmp_path,monkeypatch):
    import companion_package_identity as identity
    root=Path(__file__).resolve().parents[1]
    names=('data/auto_editions_template.json','scripts/photoshop/prepare_auto_editions.jsx',
           'scripts/photoshop/inspect_psd_editions.jsx','auto_editions_onboarding.py',
           'scripts/prepare_auto_editions.py','auto_editions.py','auto_editions_colour.py',
           'auto_editions_preparation_geometry.py','data/auto_editions_preparation_quality.json')
    for name in names:
        dest=tmp_path/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((root/name).read_bytes())
    monkeypatch.setattr(identity,'__file__',str(tmp_path/'companion_package_identity.py'))
    before=identity.generation()
    policy=tmp_path/'data/auto_editions_preparation_quality.json'
    value=json.loads(policy.read_text(encoding='utf-8'));value['references']['GLOBAL-CFP-A1']['dimensions'][0]+=1
    policy.write_text(json.dumps(value),encoding='utf-8')
    assert identity.generation()!=before
    second=identity.generation();module=tmp_path/'auto_editions_preparation_geometry.py'
    module.write_text(module.read_text(encoding='utf-8')+'\n# Changed sizing behaviour\n',encoding='utf-8')
    assert identity.generation()!=second
