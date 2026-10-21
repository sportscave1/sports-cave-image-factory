"""Resolution reports must remain informational, including for retained history."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import time
import types
from unittest.mock import Mock, patch

import pytest
from PIL import Image, ImageCms

import auto_editions as ae
import auto_editions_api as api
import auto_editions_resolution as resolution
from test_auto_editions import package
from test_auto_editions_api import request
from test_auto_editions_speed import async_test

BASELINE = '9991df9ad3f6cece5d1d7a7a52e556db2feebd53'


def snapshot(source=(7016, 4961), scale=1):
    prepared = [p * scale for p in source]
    return dict(manifest=dict(source_dimensions=list(source), dimensions=prepared,
                preparation_geometry=dict(scale=scale, method='native' if scale == 1 else 'photoshop_layered_bicubic_smoother')),
                archive_labels=dict(variant_title='Black / XL - 62 × 87 cm'))


def result(dimensions=(7016, 4961)):
    return dict(dimensions=list(dimensions), ppi_metadata=[300, 300], test_only=True, print_ready=False)


def test_sc3340_native_archived_metadata_no_regeneration_or_mutation():
    job, output = snapshot(), result()
    before = deepcopy((job, output))
    info = resolution.for_job(job, output)
    assert info['status'] == 'below_recommendation'
    assert info['exported_ppi'] == pytest.approx([211.8977, 212.1367], abs=.001)
    assert info['native_canvas_ppi'] == info['exported_ppi']
    assert info['scaling'] == 1
    assert info['supplier']['sku'] == 'GLOBAL-CFP-A1'
    assert info['output_status'] == 'TEST / NOT PRINT READY'
    assert info['dpi_metadata'] == [300, 300]
    assert (job, output) == before


def test_jake_enlargement_never_implies_better_source_detail():
    info = resolution.for_job(snapshot((2835, 2004), 4), result((11340, 8016)))
    assert info['status'] == 'meets_recommendation'
    assert info['scaling'] == 4
    assert max(info['native_canvas_ppi']) < 86
    assert min(info['exported_ppi']) > 342
    assert '4× enlargement' in info['summary'] and 'native-canvas' in info['summary']
    assert any('does not establish increased source detail' in note for note in info['notes'])
    assert info['output_status'] == 'TEST / NOT PRINT READY'


def test_native_source_meets_supplier_integer_pixel_recommendation():
    info = resolution.for_job(snapshot((9933, 7016)), result((9933, 7016)))
    assert info['status'] == 'meets_recommendation'
    assert info['native_canvas_ppi'] == info['exported_ppi']
    assert info['scaling'] == 1
    assert any('does not prove photographic detail' in note for note in info['notes'])


def test_unknown_crop_and_bleed_are_estimates_even_when_raster_meets_recommendation():
    info = resolution.for_job(snapshot((11340, 8016)), result((11340, 8016)))
    assert info['estimate'] is True and info['crop_known'] is False
    assert 'estimate before supplier crop' in info['summary']
    assert any('bleed is unknown' in note for note in info['notes'])


def test_known_crop_uses_remaining_pixels_and_supplier_canvas_including_bleed():
    # The existing verified registry contract includes bleed in printable_mm.
    spec = dict(prodigi_sku='SYNTHETIC', source='offline supplier fixture', frame='Black', size='XL',
                verification_status='Verified supplier', printable_mm=[254, 127], pixel_dimensions=[3000, 1500],
                recommended_ppi=300, bleed_mm=[3, 3, 3, 3], margins_mm=[2, 2, 2, 2],
                colour=dict(profile='sRGB', mode='RGB'))
    assert resolution.print_specifications.verified(spec)
    with patch.object(resolution.print_specifications, 'for_variant', return_value=spec):
        info = resolution.assess([6000, 3000], variant='Black / XL', source_dimensions=[6000, 3000],
                                 prepared_dimensions=[6000, 3000], preparation_geometry=dict(scale=1, method='native'),
                                 crop_bounds_px=[1500, 750, 4500, 2250])
        assert info['exported_ppi'] == [300, 300]
        assert info['native_canvas_ppi'] == [300, 300]
        assert info['estimate'] is False and info['crop_known'] is True
        assert info['supplier']['printable_mm'] == [254, 127]  # Never double-add bleed.
        cropped = resolution.assess([6000, 3000], variant='Black / XL', crop_bounds_px=[0, 0, 2000, 1000])
        assert cropped['status'] == 'below_recommendation'
        assert cropped['exported_ppi'] == [200, 200]


@pytest.mark.parametrize('dimensions,crop', [(None, None), ([7016, 4961], [-1, 0, 7016, 4961]),
                                            ([7016, 4961], [0, 0, 8000, 4961])])
def test_missing_pixels_or_invalid_crop_never_claims_resolution_verified(dimensions, crop):
    assert resolution.assess(dimensions, variant='Black / XL', crop_bounds_px=crop)['status'] == 'not_verified'


def test_legacy_missing_provenance_is_unknown_and_dpi_never_substitutes_for_pixels():
    job = snapshot()
    del job['manifest']['preparation_geometry']
    info = resolution.for_job(job, result())
    assert info['source_provenance'] == 'unknown'
    assert info['native_canvas_ppi'] is None and info['scaling'] is None
    assert resolution.for_job(snapshot(), dict(ppi_metadata=[1200, 1200]))['status'] == 'not_verified'


def test_unframed_and_unknown_sku_do_not_inherit_framed_a1():
    for variant, sku in [('Unframed / XL', None), ('Unframed / XL', 'GLOBAL-CFP-A1'),
                         ('Black / M', 'GLOBAL-CFP-A1'), ('Black / XL', 'unknown')]:
        assert resolution.assess([11340, 8016], variant=variant, sku=sku)['status'] == 'not_verified'


def test_manual_file_unknown_even_if_order_contains_unbound_dimensions():
    row = dict(variant_title='Black / XL', prodigi_code='GLOBAL-CFP-A1', dimensions=[11340, 8016])
    notice = resolution.manual_notice(row)
    assert 'Resolution not verified for manually selected asset' in notice
    assert 'GLOBAL-CFP-A1' in notice and '300 PPI' in notice
    assert 'unknown' in notice and 'crop/zoom' in notice


def test_missing_supplier_file_cannot_break_output_or_manual_information():
    with patch.object(resolution, '_editor_evidence', side_effect=OSError('unavailable')):
        assert resolution.for_job(snapshot(), result())['status'] == 'not_verified'
        assert 'existing actions are unchanged' in resolution.manual_notice(dict(variant_title='Black / XL'))


@async_test
async def test_same_size_preview_bytes_never_substitute_for_archived_original():
    import hashlib
    from auto_editions_asset_cache import output_assets
    original, preview = b'original-JPEG-bytes', b'preview--JPEG-bytes'
    assert len(original) == len(preview)
    output = dict(file_id='id:archive', revision='rev', bytes=len(original),
                  sha256=hashlib.sha256(original).hexdigest())
    assets = Mock()
    stream = Mock()
    stream.iter_content.return_value = [preview]
    assets.output_response.return_value = (dict(id='id:archive', rev='rev', size=len(original)), stream)
    row = dict(status='Ready', result=dict(output=output, filename='unchanged-TEST.jpg', retained=True))
    with patch.object(output_assets, 'copy', return_value=False), patch.object(output_assets, 'remember') as remember:
        # with_user=True requires the existing four-part snapshot.
        async def stored(*args, **kwargs):
            return ({}, dict(id='a'*64), assets, row) if kwargs.get('with_user') else (dict(id='a'*64), assets, row)
        with patch.object(api, 'stored_current', side_effect=stored), patch.object(api.runtime, 'stores', return_value=(None, Mock())):
            response = await api.download(request())
        assert response.status_code == 409
        assert b'checksum failed' in response.body
        remember.assert_not_called()
        stream.close.assert_called_once()


@async_test
async def test_historical_location_adds_information_without_enqueue_or_allocation_changes():
    job = snapshot()
    row = dict(status='Ready', result={**result(), 'output':dict(file_id='id:archive')})
    assets = Mock()
    assets.verify_output.return_value = dict(id='id:archive', rev='pinned', path_display='/saved/original.jpg')
    with patch.object(api, 'stored_current', return_value=(job, assets, row)), \
         patch.object(api.runtime, 'job_for') as resolver, patch.object(api.runtime, 'start_worker') as worker:
        response = await api.location(request())
        data = json.loads(response.body)
        assert response.status_code == 200 and data['file_id'] == 'id:archive'
        assert data['resolution_info']['status'] == 'below_recommendation'
        resolver.assert_not_called()
        worker.assert_not_called()


def test_annotation_leaves_jpeg_bytes_icc_dpi_encoding_and_number_placement_exact(tmp_path):
    # Run the actual original renderer from this task's unmodified HEAD and the
    # working renderer on the same fixture, with an embedded ICC profile.
    before_code = subprocess.check_output(['git', 'show', BASELINE + ':auto_editions.py'], encoding='utf-8')
    baseline = types.ModuleType('baseline_editions')
    exec(compile(before_code, 'baseline_editions.py', 'exec'), baseline.__dict__)
    manifest = package(tmp_path)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for name in ['master.png', 'number-1.png', 'number-2.png']:
        with Image.open(tmp_path / name) as image:
            image.save(tmp_path / name, icc_profile=profile)
        asset = manifest['master'] if name == 'master.png' else manifest['patches'][name.split('-')[1].split('.')[0]]
        asset['sha256'] = ae.file_hash(tmp_path / name)
    original = baseline.render_jpg(manifest, tmp_path, 2, tmp_path / 'before.jpg')
    current = ae.render_jpg(manifest, tmp_path, 2, tmp_path / 'after.jpg')
    resolution.for_job(dict(manifest=manifest), current)
    assert (tmp_path / 'before.jpg').read_bytes() == (tmp_path / 'after.jpg').read_bytes()
    assert original['sha256'] == current['sha256']
    with Image.open(tmp_path / 'after.jpg') as image:
        assert image.info['icc_profile'] == profile and image.info['dpi'] == (300, 300)
        assert set(v for table in image.quantization.values() for v in table) == {1}
        assert image.layer == [(1, 1, 1, 0), (2, 1, 1, 1), (3, 1, 1, 1)]
    with ae.compose(manifest, tmp_path, 2) as image:
        assert image.getpixel((70, 60)) == (255, 0, 0)
        assert image.getpixel((69, 60)) == (0, 0, 128)
    assert current['print_ready'] is False


def test_download_and_fulfilment_guards_unchanged_from_before_update():
    def functions(code):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(code).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    root = Path(__file__).resolve().parents[1]
    for name in ['auto_editions_cloud.py', 'auto_editions_jobs.py',
                 'auto_editions_store.py', 'auto_editions_runtime.py', 'auto_editions_onboarding.py',
                 'auto_editions_quality.py', 'print_jpg.py', 'print_specifications.py']:
        before = subprocess.check_output(['git', 'show', BASELINE + ':' + name], encoding='utf-8')
        assert (root / name).read_text(encoding='utf-8') == before
    for name, protected in [('auto_editions.py', ['compose','render_jpg','compare_reference','compare_original_outside_number']),
                            ('auto_editions_api.py', ['download', 'same_allocation', 'stored_current', 'start', 'retry']),
                            ('os_pages.py', ['prodigi_completion_blockers', 'prodigi_manual_override_eligibility',
                                             'prodigi_complete_with_manual_override', 'render_prodigi_page'])]:
        before = functions(subprocess.check_output(['git', 'show', BASELINE + ':' + name], encoding='utf-8'))
        after = functions((root / name).read_text(encoding='utf-8'))
        for fn in protected:
            assert after[fn] == before[fn], fn


def test_cached_information_cost():
    job, output = snapshot(), result()
    resolution.for_job(job, output)
    started = time.perf_counter()
    for _ in range(1000):
        resolution.for_job(job, output)
    # Broad regression guard; report measured cost separately in local evidence.
    assert time.perf_counter() - started < 1
