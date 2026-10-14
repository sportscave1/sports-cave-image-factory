from copy import deepcopy
import json
from pathlib import Path

import pytest
from PIL import Image
import auto_editions as ae


def package(tmp_path):
    Image.new('RGB', (200, 100), 'navy').save(tmp_path / 'master.png')
    Image.new('RGB', (20, 10), 'white').save(tmp_path / 'number-1.png')
    Image.new('RGB', (20, 10), 'red').save(tmp_path / 'number-2.png')
    def asset(name):
        return dict(name=name, sha256=ae.file_hash(tmp_path / name))
    return dict(schema_version=1, strategy='photoshop_number_patches',
                source=ae.source_identity('gid://shopify/Product/123',
                    dict(id='id:example', rev='abc123', content_hash='a'*64)),
                dimensions=[200, 100], source_dimensions=[200, 100], upscaled=False,
                number_region=[70, 60, 90, 70], edition_total=2,
                master=asset('master.png'), patches={str(n): asset(f'number-{n}.png') for n in (1,2)})


def test_compositor_uses_individual_position_and_changes_only_patch(tmp_path):
    m = package(tmp_path)
    with ae.compose(m, tmp_path, 2) as image:
        assert image.getpixel((70,60)) == (255,0,0)
        assert image.getpixel((69,60)) == (0,0,128)
        assert image.getpixel((90,60)) == (0,0,128)
        image.save(tmp_path/'reference.png')
    assert ae.compare_reference(m,tmp_path,2,tmp_path/'reference.png')['pixel_exact']
    ae.render_jpg(m,tmp_path,2,tmp_path/'output.jpg')
    with Image.open(tmp_path/'output.jpg') as output:
        assert output.format == 'JPEG' and output.size == (200,100)


def test_reference_detects_unrelated_artwork_changes(tmp_path):
    m = package(tmp_path)
    with ae.compose(m,tmp_path,2) as image:
        image.putpixel((1,1),(0,255,0)); image.save(tmp_path/'reference.png')
    with pytest.raises(ValueError,match='differs'):
        ae.compare_reference(m,tmp_path,2,tmp_path/'reference.png')


def test_original_outside_number_is_preserved(tmp_path):
    m=package(tmp_path)
    assert ae.compare_original_outside_number(m,tmp_path,2,tmp_path/'master.png')['outside_number_exact']
    with Image.open(tmp_path/'master.png') as image:
        image.putpixel((1,1),(0,255,0));image.save(tmp_path/'original-changed.png')
    with pytest.raises(ValueError,match='outside'):
        ae.compare_original_outside_number(m,tmp_path,2,tmp_path/'original-changed.png')


@pytest.mark.parametrize('number',[True,0,3,'2',1.5])
def test_invalid_number_rejected(tmp_path, number):
    with pytest.raises(ValueError): ae.compose(package(tmp_path),tmp_path,number)


def test_source_and_assets_are_immutable(tmp_path):
    m = package(tmp_path)
    (tmp_path/'number-2.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'): ae.compose(m,tmp_path,2)


def test_no_whole_image_patches_or_path_escape(tmp_path):
    m = package(tmp_path)
    m['number_region']=[0,0,200,100]
    with pytest.raises(ValueError,match='10%'): ae.validate_manifest(m)
    with pytest.raises(ValueError,match='asset name'):
        ae.asset_path(tmp_path,dict(name='../outside.png',sha256='a'*64))


def test_no_stale_approval_or_supplier_certification(tmp_path):
    m = package(tmp_path)
    assert ae.status(m)=='NOT CONFIGURED'
    approval=dict(actor_id='admin',preparation_hash=ae.fingerprint(m),pixel_exact=True,visual_approved=True)
    assert ae.status(m,approval)=='TEST READY'
    m['number_region']=[71,60,91,70]
    assert ae.status(m,approval)=='NOT CONFIGURED'


def test_actual_template_structure_and_no_coordinate_default():
    reference=ae.reference_template()
    layout=ae.inspect_layout(dict(document=reference['document'],layers=reference['layers']))
    assert layout['dimensions']==[11812,8350]
    moved=deepcopy(reference['layers'])
    for layer in moved:
        if layer['path'][-1]['name'] in ('SC_EDITION_NUMBER','SC_EDITION_PLAQUE'):
            layer['bounds_px']=[v-500 if i in (0,2) else v for i,v in enumerate(layer['bounds_px'])]
    result=ae.inspect_layout(dict(document=reference['document'],layers=moved))
    assert result['number']['bounds_px'][0]==layout['number']['bounds_px'][0]-500


def test_duplicate_or_nested_number_never_guessed():
    reference=ae.reference_template()
    layers=deepcopy(reference['layers'])
    layers.append(deepcopy(layers[0]))
    with pytest.raises(ValueError,match='exactly one'):
        ae.inspect_layout(dict(document=reference['document'],layers=layers))
    layers=deepcopy(reference['layers']); layers[0]['smart_object_chain']=[{'layer_id':99}]
    with pytest.raises(ValueError,match='nested'):
        ae.inspect_layout(dict(document=reference['document'],layers=layers))
