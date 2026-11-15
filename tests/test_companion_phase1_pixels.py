"""Proof batching must preserve rejection, identity and serialization fences."""
import json
from unittest.mock import patch

import pytest
from PIL import Image

import auto_editions as ae
from test_auto_editions import package


def fixture(root):
    manifest = package(root)
    Image.new('RGB', (20, 10), 'green').save(root/'number-3.png')
    manifest['edition_total'] = 3
    manifest['patches']['3'] = dict(name='number-3.png', sha256=ae.file_hash(root/'number-3.png'))
    for number in (1, 2, 3):
        with ae.compose(manifest, root, number) as image:
            image.save(root/f'reference-{number}.png')
    with Image.open(root/'master.png') as image:
        image.save(root/'original.png')
    return manifest


def legacy(manifest, root, number):
    return ([ae.compare_reference(manifest, root, n, root/f'reference-{n}.png')
             for n in sorted({1, number, manifest['edition_total']})],
            ae.compare_original_outside_number(manifest, root, number, root/'original.png'))


@pytest.mark.parametrize('number', [1, 2, 3])
def test_same_independent_proofs_and_unchanged_files(tmp_path, number):
    manifest = fixture(tmp_path)
    before = {p.name: ae.file_hash(p) for p in tmp_path.iterdir()}
    assert ae.verify_preparation_pixels(manifest, tmp_path, number) == legacy(manifest, tmp_path, number)
    assert before == {p.name: ae.file_hash(p) for p in tmp_path.iterdir()}


@pytest.mark.parametrize('name', ['master.png', 'number-1.png', 'number-2.png', 'number-3.png'])
def test_pinned_asset_tampering_is_never_reused(tmp_path, name):
    manifest = fixture(tmp_path)
    ae.verify_preparation_pixels(manifest, tmp_path, 2)
    (tmp_path/name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        ae.verify_preparation_pixels(manifest, tmp_path, 2)


@pytest.mark.parametrize('name', ['reference-1.png', 'reference-2.png', 'reference-3.png', 'original.png'])
def test_any_outside_artwork_change_is_rejected(tmp_path, name):
    manifest = fixture(tmp_path)
    with Image.open(tmp_path/name) as image:
        image.putpixel((1, 1), (1, 255, 5))
        image.save(tmp_path/name)
    with pytest.raises(ValueError, match='differs|outside'):
        ae.verify_preparation_pixels(manifest, tmp_path, 2)


@pytest.mark.parametrize('name', ['reference-2.png', 'number-2.png', 'original.png'])
def test_profile_change_is_rejected(tmp_path, name):
    manifest = fixture(tmp_path)
    with Image.open(tmp_path/name) as image:
        image.save(tmp_path/name, icc_profile=b'changed-profile')
    if name == 'number-2.png':
        manifest['patches']['2']['sha256'] = ae.file_hash(tmp_path/name)
    with pytest.raises(ValueError, match='profile'):
        ae.verify_preparation_pixels(manifest, tmp_path, 2)


def test_each_call_decodes_master_once_and_rebinds_identity(tmp_path):
    manifest = fixture(tmp_path)
    original = Image.open
    opened = []
    def observed(path, *args, **kwargs):
        opened.append(str(path))
        return original(path, *args, **kwargs)
    with patch('PIL.Image.open', side_effect=observed):
        proofs, _ = ae.verify_preparation_pixels(manifest, tmp_path, 2)
    assert sum(p.endswith('master.png') for p in opened) == 1
    manifest['source']['revision'] = 'abc124'
    manifest['template_revision'] = 'reviewed-template-2'
    new, _ = ae.verify_preparation_pixels(manifest, tmp_path, 2)
    assert new[0]['preparation_hash'] != proofs[0]['preparation_hash']
    assert new[0]['preparation_hash'] == ae.fingerprint(manifest)


@pytest.mark.parametrize('number', [True, 0, 4, '2', 1.5])
def test_invalid_edition_rejected(tmp_path, number):
    with pytest.raises(ValueError):
        ae.verify_preparation_pixels(fixture(tmp_path), tmp_path, number)
